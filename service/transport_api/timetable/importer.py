"""Load the national GTFS feed into Postgres.

    python -m transport_api.timetable.importer            # newest feed
    python -m transport_api.timetable.importer feed.zip   # a file at hand

The rows go into a fresh schema, `gtfs_next`, and that schema replaces `gtfs`
in one transaction at the end. A request never sees half a timetable, and an
import that fails leaves the previous one answering.

Only the days in the window are loaded (`GTFS_PAST_DAYS` back, `GTFS_DAYS`
ahead, or to the end of the feed when that is 0): a trip that runs on none of
them is skipped, along with its stop times. At least yesterday is in, because
a trip of yesterday's service day can still be running after midnight.

The national timetable is published per timetable year, which changes in
mid-December, and the next year's feed appears in the autumn. A window that
reaches across the change is read from both feeds, merged into one
(`write_window_feed`); that merged window is what both the database and the
router load.
"""

import argparse
import asyncio
import csv
import io
import logging
import time
import zipfile
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from importlib import resources
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

import asyncpg
import httpx

from .. import settings
from . import fetch_log
from .names import mode_of, normalize, operator_name

log = logging.getLogger("transport_api.timetable.importer")

ZURICH = ZoneInfo(settings.TIMEZONE)


def sql(name: str) -> str:
    return resources.files(__package__).joinpath(name).read_text()


# --------------------------------------------------------------------------
# Reading the feed
# --------------------------------------------------------------------------


def rows(feed: zipfile.ZipFile, name: str) -> Iterator[dict[str, str]]:
    """The rows of one file, streamed straight out of the archive.

    The Swiss files start with a byte-order mark, which `utf-8-sig` drops so
    that the first column is called what it says.
    """
    with feed.open(name) as raw:
        yield from csv.DictReader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))


def seconds(clock: str) -> int:
    """`25:10:00` -> 90600. Past midnight is past 24, as GTFS writes it."""
    hours, minutes, secs = clock.split(":")
    return int(hours) * 3600 + int(minutes) * 60 + int(secs)


def service_days(feed: zipfile.ZipFile, first: date, last: date) -> dict[str, list[date]]:
    """Each service, and the days in the window it runs on.

    calendar.txt gives the weekly pattern over a period; calendar_dates.txt
    adds (1) and removes (2) single days. The Swiss feed has eleven million of
    the latter, so they are compared as strings before anything is parsed.
    """
    window = [first + timedelta(days=n) for n in range((last - first).days + 1)]
    weekdays = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

    days: dict[str, set[date]] = {}
    for row in rows(feed, "calendar.txt"):
        start = datetime.strptime(row["start_date"], "%Y%m%d").date()
        end = datetime.strptime(row["end_date"], "%Y%m%d").date()
        running = {
            day for day in window if start <= day <= end and row[weekdays[day.weekday()]] == "1"
        }
        days[row["service_id"]] = running

    low, high = first.strftime("%Y%m%d"), last.strftime("%Y%m%d")
    for row in rows(feed, "calendar_dates.txt"):
        stamp = row["date"]
        if not low <= stamp <= high:
            continue
        day = datetime.strptime(stamp, "%Y%m%d").date()
        if row["exception_type"] == "1":
            days.setdefault(row["service_id"], set()).add(day)
        else:
            days.get(row["service_id"], set()).discard(day)

    return {service: sorted(running) for service, running in days.items() if running}


@dataclass
class Trip:
    idx: int
    trip_id: str
    route: int
    service: int
    headsign: str | None
    short_name: str | None
    mode: str | None
    first_seq: int = 0
    last_seq: int = 0
    last_stop: int = 0
    seen: bool = False


@dataclass
class Feed:
    """What is held in memory while stop_times streams past."""

    agencies: dict[str, int] = field(default_factory=dict)
    routes: dict[str, tuple] = field(default_factory=dict)
    stops: dict[str, int] = field(default_factory=dict)
    services: dict[str, int] = field(default_factory=dict)
    trips: dict[str, Trip] = field(default_factory=dict)
    # Trips run by frequencies.txt: their stop times are a template, not a run.
    frequencies: dict[str, list[tuple[int, int, int]]] = field(default_factory=dict)
    templates: dict[str, list[tuple]] = field(default_factory=dict)


def stop_time_records(feed: zipfile.ZipFile, state: Feed) -> Iterator[tuple]:
    """stop_times.txt as (trip, seq, stop, arr_s, dep_s, pickup, dropoff) rows.

    Rows of trips outside the window are dropped here, which is where most of
    the 42 million go. Trips that run on a headway are held back and expanded
    once their template is complete.
    """
    trips, stops = state.trips, state.stops
    with feed.open("stop_times.txt") as raw:
        reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
        header = next(reader)
        col = {name: index for index, name in enumerate(header)}
        i_trip, i_arr, i_dep = col["trip_id"], col["arrival_time"], col["departure_time"]
        i_stop, i_seq = col["stop_id"], col["stop_sequence"]
        i_pick, i_drop = col.get("pickup_type"), col.get("drop_off_type")

        for row in reader:
            trip = trips.get(row[i_trip])
            if trip is None:
                continue
            seq = int(row[i_seq])
            stop = stops[row[i_stop]]
            arr = seconds(row[i_arr] or row[i_dep])
            dep = seconds(row[i_dep] or row[i_arr])
            pickup = int(row[i_pick] or 0) if i_pick is not None else 0
            dropoff = int(row[i_drop] or 0) if i_drop is not None else 0

            if trip.trip_id in state.frequencies:
                state.templates.setdefault(trip.trip_id, []).append(
                    (seq, stop, arr, dep, pickup, dropoff)
                )
                continue

            _extend(trip, seq, stop)
            yield (trip.idx, seq, stop, arr, dep, pickup, dropoff)

    yield from _expand_frequencies(state)


def _extend(trip: Trip, seq: int, stop: int) -> None:
    if not trip.seen or seq < trip.first_seq:
        trip.first_seq = seq
    if not trip.seen or seq > trip.last_seq:
        trip.last_seq, trip.last_stop = seq, stop
    trip.seen = True


def _expand_frequencies(state: Feed) -> Iterator[tuple]:
    """One trip per departure of a headway, each a copy of the template.

    The template's times only give the spacing between stops; each copy is
    shifted so that it leaves the first stop at its own start time. The
    template itself is not a run and is dropped.
    """
    next_idx = max((trip.idx for trip in state.trips.values()), default=-1) + 1
    for trip_id, windows in state.frequencies.items():
        template = sorted(state.templates.get(trip_id, []))
        base = state.trips.pop(trip_id)
        if not template:
            continue
        origin = template[0][3]
        for start, end, headway in windows:
            for departure in range(start, end, headway):
                copy = Trip(
                    idx=next_idx,
                    trip_id=f"{trip_id}@{departure}",
                    route=base.route,
                    service=base.service,
                    headsign=base.headsign,
                    short_name=base.short_name,
                    mode=base.mode,
                )
                next_idx += 1
                state.trips[copy.trip_id] = copy
                shift = departure - origin
                for seq, stop, arr, dep, pickup, dropoff in template:
                    _extend(copy, seq, stop)
                    yield (copy.idx, seq, stop, arr + shift, dep + shift, pickup, dropoff)


# --------------------------------------------------------------------------
# Fetching it
# --------------------------------------------------------------------------


def feed_name(url: str) -> str | None:
    """The file name the permalink currently points at, without downloading.

    None when there is no such feed (yet): the permalink of a timetable year
    that has not been published answers 404.
    """
    with httpx.Client(follow_redirects=False, timeout=30) as client:
        response = client.get(url)
        if response.status_code == 404:
            return None
        target = response.headers.get("location") if response.is_redirect else url
    return Path(urlparse(target).path).name


def window_of(today: date, days: int, past: int) -> tuple[date, date | None]:
    """The first day and the last one (None: to the end of the feeds)."""
    return today - timedelta(days=past), (today + timedelta(days=days) if days > 0 else None)


def feed_urls(url: str, first: date, last: date | None) -> list[str]:
    """The permalinks of the timetable years a window may touch.

    `url` names one feed, or every year's with `{year}` in it. A timetable
    year ends in mid-December, so a day in December can belong to the next
    one; the candidates run from the first day's year to the year after the
    last day's. Those not published come back empty from feed_name.
    """
    if "{year}" not in url:
        return [url]
    end = last or first + timedelta(days=366)
    return [url.format(year=year) for year in range(first.year, end.year + 2)]


def feed_sources(url: str, first: date, last: date | None) -> list[tuple[str, str]]:
    """(permalink, file name) of the feeds that exist for the window, oldest first."""
    found: dict[str, str] = {}
    for candidate in feed_urls(url, first, last):
        name = feed_name(candidate)
        if name and name not in found.values():
            found[candidate] = name
    return list(found.items())


def download(url: str, cache: Path) -> Path:
    """The newest feed on disk, fetched only if it is not there already."""
    cache.mkdir(parents=True, exist_ok=True)
    name = feed_name(url)
    path = cache / name
    if path.exists():
        log.info("feed %s already downloaded", name)
        return path

    partial = path.with_suffix(".part")
    with httpx.stream("GET", url, follow_redirects=True, timeout=300) as response:
        response.raise_for_status()
        with partial.open("wb") as out:
            for chunk in response.iter_bytes(1 << 20):
                out.write(chunk)
    partial.rename(path)
    # A feed is a few hundred megabytes. Two timetable years with the one
    # before the newest of each stay: those may still be the loaded ones,
    # waiting for real time to move on.
    feeds = [p for p in cache.glob("*.zip") if not p.name.startswith(WINDOW_PREFIX)]
    for old in sorted(feeds, key=lambda p: p.stat().st_mtime)[:-KEPT_FEEDS]:
        old.unlink()
    log.info("downloaded %s (%d MB)", name, path.stat().st_size >> 20)
    return path


# --------------------------------------------------------------------------
# The window, for the router
# --------------------------------------------------------------------------

WINDOW_PREFIX = "window_"

# Feed files kept in the cache: two timetable years, two versions each.
KEPT_FEEDS = 4

# Files of the feed copied whole; the others are cut to the trips that run.
WHOLE = ("agency.txt", "routes.txt", "stops.txt", "feed_info.txt")


def write_window_feed(
    sources: Path | list[Path],
    target: Path,
    first: date,
    last: date | None,
    walk_sets_transfer: bool = False,
) -> dict:
    """One GTFS zip with only the trips that run between `first` and `last`.

    For the router and the database alike: MOTIS reads the whole feed into
    memory before it looks at any date, and the year's 42 million stop times
    need more than 3.5 GB to import - more than either server can spare.

    `sources` may be two timetable years. Each then gives the days it is valid
    for (the newer one where they overlap), and they are written as one feed:
    stops are shared (the newer name wins), the ids of calendars are made
    unique by the feed's version, and route or trip ids only when the two
    feeds share one - trip ids are what real time is matched by, and the
    Swiss ones carry their year already. `last` None runs to the end of the
    feeds. Written to a temporary name and renamed, so that the router never
    sees half a file. `walk_sets_transfer`: see walks_set_transfer_times.

    Returns the rows written per file, and `first`, `last` and `version` of
    the window.
    """
    paths = [sources] if isinstance(sources, (str, Path)) else list(sources)
    feeds = [zipfile.ZipFile(path) for path in paths]
    try:
        return _write_window(feeds, target, first, last, walk_sets_transfer)
    finally:
        for feed in feeds:
            feed.close()


@dataclass
class _Part:
    """One source feed's share of a window."""

    feed: zipfile.ZipFile
    version: str
    start: date
    end: date
    first: date = date.min
    last: date = date.min
    services: set = field(default_factory=set)
    trips: set = field(default_factory=set)
    rename: dict = field(default_factory=dict)  # column -> (prefix, ids to prefix or None = all)
    tangled: set = field(default_factory=set)  # trips whose stay-seated transfers are dropped


def _feed_dates(feed: zipfile.ZipFile) -> tuple[str, date, date]:
    info = next(rows(feed, "feed_info.txt"), {}) if "feed_info.txt" in feed.namelist() else {}
    start = datetime.strptime(info.get("feed_start_date") or "19700101", "%Y%m%d").date()
    end = datetime.strptime(info.get("feed_end_date") or "99991231", "%Y%m%d").date()
    return info.get("feed_version") or "", start, end


STAY_SEATED = "4"
# The most ways a vehicle may go on from one trip, staying seated, in a day.
# A normal day of the Swiss feed has at most 78; 12 December 2026, the last
# day of the 2026 feed, has trips of one bus company with four successors
# each, a million chains from one trip - and MOTIS 2.11.4, which follows
# every chain when it imports, never finishes.
MAX_STAY_SEATED_CHAINS = 10_000


def tangled_trips(feed: zipfile.ZipFile, days: dict, service_of: dict) -> set:
    """Trips from which staying seated branches into too many chains on some day.

    Their stay-seated transfers are left out of the window: passengers are
    told to change where they could have stayed on, and the router imports.
    """
    if "transfers.txt" not in feed.namelist():
        return set()
    edges: dict[tuple[str, str], None] = {}
    for row in rows(feed, "transfers.txt"):
        if row.get("transfer_type") != STAY_SEATED:
            continue
        a, b = row.get("from_trip_id", ""), row.get("to_trip_id", "")
        if a in service_of and b in service_of:
            edges[(a, b)] = None
    on_day: dict[date, dict[str, list[str]]] = {}
    running = {service: set(dates) for service, dates in days.items()}
    for a, b in edges:
        for day in running.get(service_of[a], set()) & running.get(service_of[b], set()):
            on_day.setdefault(day, {}).setdefault(a, []).append(b)

    tangled: set = set()
    for day, out in on_day.items():
        counted: dict[str, int] = {}
        found = {
            trip
            for trip in out
            if _chains(trip, out, counted, frozenset()) > MAX_STAY_SEATED_CHAINS
        }
        if found:
            log.warning(
                "%d trips branch into over %d stay-seated chains on %s; transfers left out",
                len(found),
                MAX_STAY_SEATED_CHAINS,
                day,
            )
        tangled |= found
    return tangled


def _chains(trip: str, out: dict, counted: dict, seen: frozenset) -> int:
    """The chains of trips a vehicle may run from `trip` on, counted up to just past the limit."""
    if trip in counted:
        return counted[trip]
    total = 1
    for successor in out.get(trip, ()):
        if successor not in seen:  # a cycle, in bad data, counts once
            total += _chains(successor, out, counted, seen | {trip})
        if total > MAX_STAY_SEATED_CHAINS:
            break
    counted[trip] = total
    return total


def _write_window(feeds, target: Path, first: date, last: date | None, walks: bool) -> dict:
    parts = sorted((_Part(feed, *_feed_dates(feed)) for feed in feeds), key=lambda part: part.start)
    for i, part in enumerate(parts):
        part.first = max(first, part.start)
        part.last = part.end if last is None else min(last, part.end)
        if i + 1 < len(parts):
            part.last = min(part.last, parts[i + 1].start - timedelta(days=1))
    parts = [part for part in parts if part.first <= part.last]
    if not parts:
        raise ValueError(f"no feed covers {first}..{last}")

    for part in parts:
        days = service_days(part.feed, part.first, part.last)
        part.services = set(days)
        service_of = {
            row["trip_id"]: row["service_id"]
            for row in rows(part.feed, "trips.txt")
            if row["service_id"] in part.services
        }
        part.trips = set(service_of)
        part.tangled = tangled_trips(part.feed, days, service_of)

    # Ids the later feeds must change so as not to meet the earlier ones'.
    seen_routes: set = set()
    seen_trips: set = set()
    for i, part in enumerate(parts):
        routes = {row["route_id"] for row in rows(part.feed, "routes.txt")}
        if i:
            prefix = f"{part.version or i}:"
            part.rename["service_id"] = (prefix, None)
            # Block ids are bare numbers, the same in both years (all 62 544 of
            # 2027 are in 2026): kept apart, so that no vehicle runs on from a
            # trip of one year into one of the other.
            part.rename["block_id"] = (prefix, None)
            if routes & seen_routes:
                part.rename["route_id"] = (prefix, routes & seen_routes)
            if part.trips & seen_trips:
                log.warning("%d trip ids repeat across feeds", len(part.trips & seen_trips))
                part.rename["trip_id"] = (prefix, part.trips & seen_trips)
        seen_routes |= routes
        seen_trips |= part.trips

    def trip_ok(part):
        def check(row, col, *names):
            return all(
                name not in col or row[col[name]] == "" or row[col[name]] in part.trips
                for name in names
            )

        return check

    def keep_for(part, name):
        low, high = part.first.strftime("%Y%m%d"), part.last.strftime("%Y%m%d")
        services, trips, ok = part.services, part.trips, trip_ok(part)

        def calendar(r, c):
            # Kept rows are cut to this feed's share of the window, so that a
            # calendar running on past the timetable change does not reach
            # into the next year's days.
            if r[c["service_id"]] not in services:
                return False
            r[c["start_date"]] = max(r[c["start_date"]], low)
            r[c["end_date"]] = min(r[c["end_date"]], high)
            return True

        return {
            "calendar.txt": calendar,
            "calendar_dates.txt": lambda r, c: (
                r[c["service_id"]] in services and low <= r[c["date"]] <= high
            ),
            "trips.txt": lambda r, c: r[c["trip_id"]] in trips,
            "stop_times.txt": lambda r, c: r[c["trip_id"]] in trips,
            "frequencies.txt": lambda r, c: r[c["trip_id"]] in trips,
            "transfers.txt": lambda r, c: (
                ok(r, c, "from_trip_id", "to_trip_id")
                and not (
                    "transfer_type" in c
                    and "from_trip_id" in c
                    and r[c["transfer_type"]] == STAY_SEATED
                    and r[c["from_trip_id"]] in part.tangled
                )
            ),
        }.get(name)

    names = []
    for part in parts:
        names += [n for n in part.feed.namelist() if n not in names]
    # The newest first for the files whose rows are merged by key, so that its
    # version of a stop or an operator is the one kept.
    by_key = {"stops.txt": ("stop_id",), "agency.txt": ("agency_id",)}

    counts: dict = {}
    partial = target.with_name(target.name + ".part")
    with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as out:
        for name in names:
            if name == "feed_info.txt":
                continue
            if name not in WHOLE and keep_for(parts[0], name) is None:
                continue
            ordered = list(reversed(parts)) if name in by_key else parts
            sources = [
                (part, keep_for(part, name)) for part in ordered if name in part.feed.namelist()
            ]
            rewrite = walks_set_transfer_times if walks and name == "transfers.txt" else None
            counts[name] = _merge_rows(out, name, sources, by_key.get(name), rewrite)
        out.writestr("feed_info.txt", _feed_info(parts))

    partial.rename(target)
    counts.update(
        first=parts[0].first,
        last=parts[-1].last,
        version="+".join(part.version for part in parts if part.version) or None,
    )
    return counts


def _feed_info(parts: list[_Part]) -> str:
    text = io.StringIO()
    writer = csv.writer(text, quoting=csv.QUOTE_ALL)
    writer.writerow(
        [
            "feed_publisher_name",
            "feed_publisher_url",
            "feed_lang",
            "feed_start_date",
            "feed_end_date",
            "feed_version",
        ]
    )
    info = next(rows(parts[-1].feed, "feed_info.txt"), {})
    writer.writerow(
        [
            info.get("feed_publisher_name", ""),
            info.get("feed_publisher_url", ""),
            info.get("feed_lang", ""),
            parts[0].first.strftime("%Y%m%d"),
            parts[-1].last.strftime("%Y%m%d"),
            "+".join(part.version for part in parts if part.version),
        ]
    )
    return text.getvalue()


def _merge_rows(out: zipfile.ZipFile, name: str, sources, key, rewrite) -> int:
    """The kept rows of one file from every source, under one header.

    Columns are matched by name; a column only one feed has stays empty in
    the other's rows. With `key`, a row whose key an earlier source already
    gave is left out. `rewrite` gets all rows at once (the transfers).
    """
    readers = []
    header: list[str] = []
    for part, keep in sources:
        raw = part.feed.open(name)
        reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
        columns = next(reader, [])
        header += [c for c in columns if c not in header]
        readers.append((part, keep, raw, reader, {c: i for i, c in enumerate(columns)}))

    def renamed(part, col):
        """(output index, prefix, only these ids) per renamed column of this file."""
        found = []
        for column, (prefix, only) in part.rename.items():
            for out_name in (column, f"from_{column}", f"to_{column}"):
                if out_name in col:
                    found.append((header.index(out_name), prefix, only))
        return found

    seen: set = set()
    kept = 0
    collected = [] if rewrite is not None else None
    # Zip64 from the start: two years' stop times are over 4 GB uncompressed
    # before they are cut, and the size is not known when writing begins.
    with out.open(name, "w", force_zip64=True) as sink:
        text = io.TextIOWrapper(sink, encoding="utf-8", newline="")
        writer = csv.writer(text, quoting=csv.QUOTE_ALL)
        writer.writerow(header)
        for part, keep, raw, reader, col in readers:
            same = list(col) == header[: len(col)]
            positions = [col.get(c) for c in header]
            changes = renamed(part, col)
            key_at = [header.index(k) for k in key] if key else None
            for row in reader:
                if keep is not None and not keep(row, col):
                    continue
                if not same or len(row) != len(header):
                    row = [row[i] if i is not None and i < len(row) else "" for i in positions]
                for at, prefix, only in changes:
                    value = row[at]
                    if value and (only is None or value in only):
                        row[at] = prefix + value
                if key_at is not None:
                    k = tuple(row[i] for i in key_at)
                    if k in seen:
                        continue
                    seen.add(k)
                if collected is not None:
                    collected.append(row)
                else:
                    writer.writerow(row)
                    kept += 1
            raw.close()
        if collected is not None:
            for row in rewrite(collected, {c: i for i, c in enumerate(header)}):
                writer.writerow(row)
                kept += 1
        text.flush()
        text.detach()
    return kept


# What the router assumes for a stop without a transfer time of its own.
ROUTER_TRANSFER_SECONDS = 120

# A stop's transfer time is not lowered below this: a zero would let the
# router change between any two platforms of the stop at no cost.
LEAST_TRANSFER_SECONDS = 60


def walks_set_transfer_times(transfers: list[list[str]], col: dict[str, int]) -> list[list[str]]:
    """Lower each stop's transfer time to the shortest walk that touches it.

    MOTIS times a walk between two stops as the longest of the walk and the
    transfer times at both ends, so a 5-minute walk from a station with a
    10-minute transfer time costs 10 minutes. In HAFAS, whose data this is,
    the walk replaces the transfer time. Lowering the transfer time of each
    stop to its shortest walk - leaving and arriving - makes the router take
    the walks as given, at the price of a tighter transfer within that stop.

    Only rows that hold for every trip count: walks (`transfer_type` 2
    between two stops) and transfer times (a stop to itself). A stop that
    has no transfer time of its own gets a row.
    """

    def plain(row: list[str]) -> bool:
        return all(
            name not in col or row[col[name]] == ""
            for name in ("from_route_id", "to_route_id", "from_trip_id", "to_trip_id")
        )

    def seconds(row: list[str]) -> int | None:
        value = row[col["min_transfer_time"]] if "min_transfer_time" in col else ""
        return int(value) if value.isdigit() else None

    a, b = col["from_stop_id"], col["to_stop_id"]
    own: dict[str, int] = {}
    walk: dict[str, int] = {}
    for row in transfers:
        if not plain(row) or row[col["transfer_type"]] != "2" or (time := seconds(row)) is None:
            continue
        if row[a] == row[b]:
            own[row[a]] = time
        else:
            for stop in (row[a], row[b]):
                walk[stop] = min(walk.get(stop, time), time)

    lowered = {
        stop: max(time, LEAST_TRANSFER_SECONDS)
        for stop, time in walk.items()
        if max(time, LEAST_TRANSFER_SECONDS) < own.get(stop, ROUTER_TRANSFER_SECONDS)
    }
    result, written = [], set()
    for row in transfers:
        if plain(row) and row[a] == row[b] and row[a] in lowered and seconds(row) is not None:
            row = list(row)
            row[col["min_transfer_time"]] = str(lowered[row[a]])
            written.add(row[a])
        result.append(row)
    for stop, time in lowered.items():
        if stop in written:
            continue
        row = [""] * len(col)
        row[a] = row[b] = stop
        row[col["transfer_type"]] = "2"
        row[col["min_transfer_time"]] = str(time)
        result.append(row)
    return result


def window_feed_name(version: str | None, first: date, walk_sets_transfer: bool = False) -> str:
    """Changes with the feed, the window and the transfers, so the router follows all three."""
    walks = "_walks" if walk_sets_transfer else ""
    return f"{WINDOW_PREFIX}{version or 'feed'}_{first:%Y%m%d}{walks}.zip"


def build_window(sources: list[Path], directory: Path, first: date, last: date | None) -> Path:
    """The merged window of `sources`, written into `directory` under its name."""
    directory.mkdir(parents=True, exist_ok=True)
    walks = settings.GTFS_WALK_SETS_TRANSFER
    building = directory / f"{WINDOW_PREFIX}building.zip"
    counts = write_window_feed(sources, building, first, last, walks)
    target = directory / window_feed_name(counts["version"], counts["first"], walks)
    building.rename(target)
    log.info(
        "window %s..%s from %s: %s",
        counts["first"],
        counts["last"],
        ", ".join(p.name for p in sources),
        target.name,
    )
    return target


def publish_window(window: Path) -> None:
    """Point the router at a window.

    The router (docker/motis-run.sh) follows `CURRENT`, written once the zip
    is complete. The window before stays, in case the router is still
    importing it; older ones go.
    """
    directory = window.parent
    (directory / "CURRENT").write_text(window.name + "\n")
    windows = sorted(directory.glob(WINDOW_PREFIX + "*.zip"), key=lambda p: p.stat().st_mtime)
    for old in windows[:-2]:
        if old != window:
            old.unlink()
    log.info("window for the router: %s", window.name)


# --------------------------------------------------------------------------
# Loading it
# --------------------------------------------------------------------------


async def load(
    connection: asyncpg.Connection,
    path: Path,
    today: date,
    days: int,
    past: int = 1,
    feed_file: str | None = None,
) -> dict:
    """Read the feed at `path` into `gtfs_next` and swap it in. Returns counts.

    `feed_file` is what is recorded as loaded, when `path` is a window merged
    from other files: their names, joined by `+`.
    """
    started = time.monotonic()
    first = today - timedelta(days=past)

    with zipfile.ZipFile(path) as feed:
        info = next(rows(feed, "feed_info.txt"), {})
        feed_start = datetime.strptime(info.get("feed_start_date", "19700101"), "%Y%m%d").date()
        feed_end = datetime.strptime(info.get("feed_end_date", "99991231"), "%Y%m%d").date()
        first = max(first, feed_start)
        last = feed_end if days <= 0 else min(today + timedelta(days=days), feed_end)

        await connection.execute(sql("schema.sql"))
        await connection.execute(sql("realtime.sql"))
        state = Feed()

        running = service_days(feed, first, last)
        state.services = {service: index for index, service in enumerate(sorted(running))}
        await _copy(
            connection,
            "service_dates",
            ("service", "day"),
            ((state.services[s], day) for s, ds in running.items() for day in ds),
        )

        agency_rows = []
        for index, row in enumerate(rows(feed, "agency.txt")):
            state.agencies[row["agency_id"]] = index
            agency_rows.append((index, operator_name(row["agency_id"], row["agency_name"])))
        await _copy(connection, "agency", ("idx", "name"), agency_rows)

        route_rows = []
        for index, row in enumerate(rows(feed, "routes.txt")):
            route_type = int(row["route_type"])
            mode = mode_of(route_type)
            state.routes[row["route_id"]] = (index, mode)
            route_rows.append(
                (
                    index,
                    state.agencies.get(row.get("agency_id", "")),
                    row.get("route_short_name") or None,
                    row.get("route_desc") or None,
                    route_type,
                    mode,
                )
            )
        await _copy(
            connection,
            "routes",
            ("idx", "agency", "short_name", "category", "route_type", "mode"),
            route_rows,
        )

        stop_rows = list(rows(feed, "stops.txt"))
        state.stops = {row["stop_id"]: index for index, row in enumerate(stop_rows)}
        await _copy(
            connection,
            "stops",
            ("idx", "stop_id", "name", "name_norm", "lat", "lon", "station", "platform", "didok"),
            (
                (
                    state.stops[row["stop_id"]],
                    row["stop_id"],
                    row["stop_name"],
                    normalize(row["stop_name"]),
                    float(row["stop_lat"]) if row.get("stop_lat") else None,
                    float(row["stop_lon"]) if row.get("stop_lon") else None,
                    state.stops.get(row.get("parent_station") or "", state.stops[row["stop_id"]]),
                    row.get("platform_code") or None,
                    row.get("didok") or None,
                )
                for row in stop_rows
            ),
        )
        del stop_rows

        for row in rows(feed, "trips.txt"):
            service = state.services.get(row["service_id"])
            if service is None:
                continue
            route, mode = state.routes[row["route_id"]]
            state.trips[row["trip_id"]] = Trip(
                idx=len(state.trips),
                trip_id=row["trip_id"],
                route=route,
                service=service,
                headsign=row.get("trip_headsign") or None,
                short_name=row.get("trip_short_name") or None,
                mode=mode,
            )

        if "frequencies.txt" in feed.namelist():
            for row in rows(feed, "frequencies.txt"):
                if row["trip_id"] in state.trips:
                    state.frequencies.setdefault(row["trip_id"], []).append(
                        (
                            seconds(row["start_time"]),
                            seconds(row["end_time"]),
                            int(row["headway_secs"]),
                        )
                    )

        log.info(
            "window %s..%s: %d services, %d trips; streaming stop times",
            first,
            last,
            len(state.services),
            len(state.trips),
        )
        stop_times = await _copy(
            connection,
            "stop_times",
            ("trip", "seq", "stop", "arr_s", "dep_s", "pickup", "dropoff"),
            stop_time_records(feed, state),
        )

        trips = [trip for trip in state.trips.values() if trip.seen]
        await _copy(
            connection,
            "trips",
            (
                "idx",
                "trip_id",
                "route",
                "service",
                "headsign",
                "short_name",
                "mode",
                "first_seq",
                "last_seq",
                "last_stop",
            ),
            (
                (
                    t.idx,
                    t.trip_id,
                    t.route,
                    t.service,
                    t.headsign,
                    t.short_name,
                    t.mode,
                    t.first_seq,
                    t.last_seq,
                    t.last_stop,
                )
                for t in trips
            ),
        )
        await connection.execute(
            "INSERT INTO gtfs_next.feed_info (feed_file, version, window_from, window_to)"
            " VALUES ($1, $2, $3, $4)",
            feed_file or path.name,
            info.get("feed_version"),
            first,
            last,
        )

    log.info("indexing")
    await connection.execute(sql("finish.sql"))
    await swap(connection)

    counts = {
        "feed": feed_file or path.name,
        "version": info.get("feed_version"),
        "first": first,
        "last": last,
        "window": f"{first}..{last}",
        "trips": len(trips),
        "stop_times": stop_times,
        "stops": len(state.stops),
        "seconds": round(time.monotonic() - started),
    }
    log.info("imported %s", counts)
    return counts


async def _copy(
    connection: asyncpg.Connection, table: str, columns: tuple[str, ...], records: Iterable
) -> int:
    result = await connection.copy_records_to_table(
        table, schema_name="gtfs_next", columns=columns, records=records
    )
    # asyncpg answers with the command tag, "COPY <n>".
    return int(result.split()[-1])


async def swap(connection: asyncpg.Connection) -> None:
    """Put `gtfs_next` in the place of `gtfs`, in one transaction.

    Queries already running keep the tables they opened; the old schema is
    dropped afterwards, which waits for them.
    """
    async with connection.transaction():
        await connection.execute("DROP SCHEMA IF EXISTS gtfs_old CASCADE")
        exists = await connection.fetchval("SELECT 1 FROM pg_namespace WHERE nspname = 'gtfs'")
        if exists:
            await connection.execute("ALTER SCHEMA gtfs RENAME TO gtfs_old")
        await connection.execute("ALTER SCHEMA gtfs_next RENAME TO gtfs")
    await connection.execute("DROP SCHEMA IF EXISTS gtfs_old CASCADE")


async def current_feed(connection: asyncpg.Connection) -> asyncpg.Record | None:
    """What is loaded now, or None before the first import."""
    exists = await connection.fetchval("SELECT to_regclass('gtfs.feed_info') IS NOT NULL")
    if not exists:
        return None
    return await connection.fetchrow("SELECT * FROM gtfs.feed_info")


async def main(sources: list[str], window_dir: str | None, window_only: bool = False) -> None:
    """Import the window: from the files given, or the feeds the window needs.

    The window is merged into one file first (`build_window`), the database is
    loaded from it, and with `window_dir` the router is pointed at it. With
    `window_only` nothing is imported: the window the database holds is
    written again from its feeds in the cache.
    """
    cache = Path(settings.GTFS_CACHE)
    today = datetime.now(ZURICH).date()
    first, last = window_of(today, settings.GTFS_DAYS, settings.GTFS_PAST_DAYS)
    connection = await asyncpg.connect(settings.DATABASE_URL)
    try:
        if window_only:
            loaded = await current_feed(connection)
            if loaded is None:
                raise SystemExit("no timetable loaded")
            paths = [Path(s) for s in sources] or [
                cache / name for name in loaded["feed_file"].split("+")
            ]
            window = build_window(
                paths, Path(window_dir or cache), loaded["window_from"], loaded["window_to"]
            )
            publish_window(window)
            return
        if sources:
            paths = [Path(s) for s in sources]
        else:
            paths = [
                download(url, cache) for url, _ in feed_sources(settings.GTFS_URL, first, last)
            ]
        window = build_window(paths, Path(window_dir or cache), first, last)
        counts = await load(
            connection,
            window,
            today,
            settings.GTFS_DAYS,
            settings.GTFS_PAST_DAYS,
            feed_file="+".join(p.name for p in paths),
        )
        await fetch_log.record(
            connection,
            "import",
            name=counts["feed"],
            bytes_=window.stat().st_size,
            items=counts["stop_times"],
            seconds=counts["seconds"],
            detail={"window": counts["window"], "trips": counts["trips"], "stops": counts["stops"]},
        )
    finally:
        await connection.close()
    if window_dir:
        publish_window(window)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "feeds", nargs="*", help="GTFS zips (one per timetable year); default: download them."
    )
    parser.add_argument(
        "--window-feed",
        metavar="DIR",
        help="Also write the loaded window as a GTFS zip for the router, and CURRENT.",
    )
    parser.add_argument(
        "--window-only",
        action="store_true",
        help="Do not import: write the loaded window for the router again (into --window-feed,"
        " default GTFS_CACHE).",
    )
    arguments = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    asyncio.run(main(arguments.feeds, arguments.window_feed, arguments.window_only))
