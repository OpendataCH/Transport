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
from .names import mode_of, normalize

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


def feed_name(url: str) -> str:
    """The file name the permalink currently points at, without downloading."""
    with httpx.Client(follow_redirects=False, timeout=30) as client:
        response = client.get(url)
        target = response.headers.get("location") if response.is_redirect else url
    return Path(urlparse(target).path).name


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
    # A feed is a few hundred megabytes. The one before the newest stays: it
    # may still be the loaded one, waiting for real time to move on.
    feeds = [p for p in cache.glob("*.zip") if not p.name.startswith(WINDOW_PREFIX)]
    for old in sorted(feeds, key=lambda p: p.stat().st_mtime)[:-2]:
        old.unlink()
    log.info("downloaded %s (%d MB)", name, path.stat().st_size >> 20)
    return path


# --------------------------------------------------------------------------
# The window, for the router
# --------------------------------------------------------------------------

WINDOW_PREFIX = "window_"

# Files of the feed copied whole; the others are cut to the trips that run.
WHOLE = ("agency.txt", "routes.txt", "stops.txt", "feed_info.txt")


def write_window_feed(
    source: Path, target: Path, first: date, last: date, walk_sets_transfer: bool = False
) -> dict[str, int]:
    """A GTFS zip with only the trips that run between `first` and `last`.

    For the router: MOTIS reads the whole feed into memory before it looks at
    any date, and the year's 42 million stop times need more than 3.5 GB to
    import - more than either server can spare. The window that the database
    holds is a quarter of that. Written to a temporary name and renamed, so
    that the router never sees half a file. `walk_sets_transfer`: see
    walks_set_transfer_times.
    """
    low, high = first.strftime("%Y%m%d"), last.strftime("%Y%m%d")
    with zipfile.ZipFile(source) as feed:
        services = set(service_days(feed, first, last))
        trips = {row["trip_id"] for row in rows(feed, "trips.txt") if row["service_id"] in services}

        # Each test gets the row and the column positions: building a dict per
        # row would cost a minute over 42 million stop times.
        def trip_ok(row: list, col: dict, *names: str) -> bool:
            return all(
                name not in col or row[col[name]] in ("",) or row[col[name]] in trips
                for name in names
            )

        keep = {
            "calendar.txt": lambda r, c: r[c["service_id"]] in services,
            "calendar_dates.txt": lambda r, c: (
                r[c["service_id"]] in services and low <= r[c["date"]] <= high
            ),
            "trips.txt": lambda r, c: r[c["trip_id"]] in trips,
            "stop_times.txt": lambda r, c: r[c["trip_id"]] in trips,
            "frequencies.txt": lambda r, c: r[c["trip_id"]] in trips,
            "transfers.txt": lambda r, c: trip_ok(r, c, "from_trip_id", "to_trip_id"),
        }
        rewrite = {"transfers.txt": walks_set_transfer_times} if walk_sets_transfer else {}
        partial = target.with_name(target.name + ".part")
        counts = {}
        with zipfile.ZipFile(partial, "w", zipfile.ZIP_DEFLATED) as out:
            for name in feed.namelist():
                if name not in WHOLE and name not in keep:
                    continue
                counts[name] = _copy_rows(feed, out, name, keep.get(name), rewrite.get(name))
    partial.rename(target)
    return counts


def _copy_rows(feed: zipfile.ZipFile, out: zipfile.ZipFile, name: str, keep, rewrite=None) -> int:
    """Copy the rows that `keep` accepts; `rewrite` gets all of them at once."""
    kept = 0
    with feed.open(name) as raw, out.open(name, "w") as sink:
        reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", newline=""))
        text = io.TextIOWrapper(sink, encoding="utf-8", newline="")
        writer = csv.writer(text, quoting=csv.QUOTE_ALL)
        header = next(reader)
        col = {name: index for index, name in enumerate(header)}
        writer.writerow(header)
        selected = (row for row in reader if keep is None or keep(row, col))
        if rewrite is not None:
            selected = iter(rewrite(list(selected), col))
        for row in selected:
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


def publish_window(source: Path, directory: Path, counts: dict) -> Path:
    """Write the window the database now holds, and point the router at it.

    The router (docker/motis-run.sh) follows `CURRENT`; it is written last,
    after the zip is complete. The window before stays, in case the router is
    still importing it; older ones go.
    """
    walks = settings.GTFS_WALK_SETS_TRANSFER
    target = directory / window_feed_name(counts.get("version"), counts["first"], walks)
    write_window_feed(source, target, counts["first"], counts["last"], walks)
    (directory / "CURRENT").write_text(target.name + "\n")
    windows = sorted(directory.glob(WINDOW_PREFIX + "*.zip"), key=lambda p: p.stat().st_mtime)
    for old in windows[:-2]:
        old.unlink()
    log.info("window for the router: %s", target.name)
    return target


# --------------------------------------------------------------------------
# Loading it
# --------------------------------------------------------------------------


async def load(
    connection: asyncpg.Connection, path: Path, today: date, days: int, past: int = 1
) -> dict:
    """Read the feed at `path` into `gtfs_next` and swap it in. Returns counts."""
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
            agency_rows.append((index, row["agency_name"]))
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
            path.name,
            info.get("feed_version"),
            first,
            last,
        )

    log.info("indexing")
    await connection.execute(sql("finish.sql"))
    await swap(connection)

    counts = {
        "feed": path.name,
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


async def main(source: str | None, window_dir: str | None, window_only: bool = False) -> None:
    connection = await asyncpg.connect(settings.DATABASE_URL)
    if window_only:
        # The window the database holds, written again from its cached feed:
        # for a change to the router's feed that should not wait for the next
        # timetable.
        try:
            loaded = await current_feed(connection)
        finally:
            await connection.close()
        if loaded is None:
            raise SystemExit("no timetable loaded")
        counts = {
            "version": loaded["version"],
            "first": loaded["window_from"],
            "last": loaded["window_to"],
        }
        path = Path(source) if source else Path(settings.GTFS_CACHE) / loaded["feed_file"]
        publish_window(path, Path(window_dir or settings.GTFS_CACHE), counts)
        return
    path = Path(source) if source else download(settings.GTFS_URL, Path(settings.GTFS_CACHE))
    try:
        counts = await load(
            connection,
            path,
            datetime.now(ZURICH).date(),
            settings.GTFS_DAYS,
            settings.GTFS_PAST_DAYS,
        )
    finally:
        await connection.close()
    if window_dir:
        publish_window(path, Path(window_dir), counts)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("feed", nargs="?", help="A GTFS zip; default: download the newest.")
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
    asyncio.run(main(arguments.feed, arguments.window_feed, arguments.window_only))
