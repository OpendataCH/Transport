"""`/v1/stationboard` (and `/v2`) from the timetable database.

A board is the stop times at the platforms of one station, on the service
days that can reach the requested moment and the day after it: today's,
yesterday's for the trips that run past midnight, and tomorrow's for a stop
that is quiet until the morning. Real-time delays come from `rt.stop_delay`,
which the ingest loop keeps current.
"""

from datetime import datetime, timedelta
from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import PlainTextResponse

from .. import errors, phptime
from ..encoding import PhpJson
from ..fields import Fields
from ..mapping import DEPRECATED_TYPES, ZURICH
from ..models import Errors, StationBoardResponse
from ..query import as_list, parameter, truthy
from . import db, occupancy
from .locations import BY_NAME, _like_escape
from .mapping import (
    highest_capacity,
    journey,
    location,
    moment,
    service_day_start,
    set_capacity,
    stop,
    trip_ref,
)
from .names import normalize

router = APIRouter()

# The default when nobody says otherwise, and the ceiling above which /v1
# refuses. Both are the PHP's.
DEFAULT_LIMIT = "40"
MAX_LIMIT = 420

# How far ahead a board looks. A quiet stop may have its next departure in
# the morning; nothing in the timetable is further away than a day. A busy
# one fills its board within the first of these, which reads a fraction of
# the rows: the longer one is only asked when the shorter falls short.
HORIZONS = (2 * 3600, 24 * 3600)
HORIZON = HORIZONS[-1]

# Rows fetched beyond `limit`, for the departures that share its last minute.
TIES = 50

BY_ID = """
SELECT idx, id, name, lat, lon FROM gtfs.station WHERE id = $1
ORDER BY departures DESC LIMIT 1
"""

# One half per service day; `{time}` is dep_s or arr_s, `{end}` the end of a
# trip that cannot be departed from (its last stop) or arrived at (its first).
# A cancelled trip, and a trip that passes this stop without calling, are left
# out - unless `{dropped}` (the showCancelled parameter) asks for them, marked.
CANCELLED = """EXISTS (
      SELECT 1 FROM rt.trip_cancelled c
      WHERE c.trip_id = t.trip_id AND c.day = ${p}::date)
  OR EXISTS (
      SELECT 1 FROM rt.stop_skipped k
      WHERE k.trip_id = t.trip_id AND k.day = ${p}::date AND k.seq = st.seq)"""

HALF = """
SELECT st.trip, st.seq, st.stop, st.arr_s, st.dep_s, ${p}::date AS day,
       ${p1}::bigint + st.{time} AS at, ({cancelled}) AS cancelled
FROM gtfs.stop_times st
JOIN gtfs.trips t ON t.idx = st.trip
JOIN gtfs.service_dates sd ON sd.service = t.service AND sd.day = ${p}::date
WHERE st.stop = ANY($1::int[])
  AND st.{time} >= ${p2} AND st.{time} < ${p3}
  AND st.seq <> t.{end}
  AND st.{flag} <> 1
  AND ($2::text[] IS NULL OR t.mode = ANY($2::text[]))
  AND ($3::boolean OR NOT ({cancelled}))
"""

TRIPS = """
SELECT t.idx, t.trip_id, t.headsign, t.short_name, t.last_seq, t.mode,
       r.short_name AS route_short_name, r.category, a.name AS operator
FROM gtfs.trips t
JOIN gtfs.routes r ON r.idx = t.route
LEFT JOIN gtfs.agency a ON a.idx = r.agency
WHERE t.idx = ANY($1::int[])
"""

# The calls of the listed trips, with the delays known for them on the day
# asked about. GTFS-RT reports a delay at some stops and means it to hold
# until the next report, so each call takes the latest report at or before
# it. A report at the stop itself gives both of its times; one carried over
# from an earlier stop is that stop's departure delay.
CALLS = """
SELECT st.trip, st.seq, st.arr_s, st.dep_s, s.platform,
       stn.id, stn.name, stn.lat, stn.lon,
       CASE WHEN d.seq = st.seq THEN coalesce(d.arrival_delay, d.departure_delay)
            ELSE coalesce(d.departure_delay, d.arrival_delay) END AS arrival_delay,
       coalesce(d.departure_delay, d.arrival_delay) AS departure_delay
FROM gtfs.stop_times st
JOIN gtfs.trips t ON t.idx = st.trip
JOIN gtfs.stops s ON s.idx = st.stop
JOIN gtfs.station stn ON stn.idx = s.station
LEFT JOIN LATERAL (
    SELECT r.seq, r.arrival_delay, r.departure_delay
    FROM rt.stop_delay r
    WHERE r.trip_id = t.trip_id AND r.day = ANY($2::date[]) AND r.seq <= st.seq
    ORDER BY r.seq DESC
    LIMIT 1
) d ON true
WHERE st.trip = ANY($1::int[])
ORDER BY st.trip, st.seq
"""

# What /v1 calls each means of transport, and the mode it is in the table.
TRANSPORTATIONS = {"train", "tram", "ship", "bus", "cableway"}


@router.get(
    "/stationboard",
    summary="Get station board",
    response_model=StationBoardResponse,
    responses={
        400: {"description": "`limit` above 420.", "content": {"text/plain": {}}},
        503: {"model": Errors, "description": "The timetable is not loaded."},
    },
)
async def station_board(
    request: Request,
    pool: Annotated[asyncpg.Pool, Depends(db.get_pool)],
    fields: Annotated[Fields, Depends(Fields.of)],
    station: Annotated[str | None, Query(description="The stop to report on.")] = None,
    id: Annotated[  # noqa: A002 - the name is part of the /v1 contract
        str | None, Query(description="The stop id, as an alternative to `station`; wins over it.")
    ] = None,
    limit: Annotated[str, Query(description="Number of departures, at most 420.")] = DEFAULT_LIMIT,
    transportations: Annotated[
        list[str] | None,
        Query(alias="transportations[]", description="Means of transport to show."),
    ] = None,
    datetime_: Annotated[
        str | None, Query(alias="datetime", description="`YYYY-MM-DD hh:mm`; now by default.")
    ] = None,
    date: Annotated[str | None, Query(description="Takes precedence over `datetime`.")] = None,
    type: Annotated[  # noqa: A002 - the name is part of the /v1 contract
        str | None, Query(description="`departure` (default) or `arrival`.")
    ] = None,
    fields_: Annotated[
        list[str] | None,
        Query(alias="fields[]", description="Keep only these parts of the answer."),
    ] = None,
    show_cancelled: Annotated[
        str | None,
        Query(
            alias="showCancelled",
            description="`1` to keep cancelled journeys, and journeys that pass the stop "
            "without calling, on the board, each marked `cancelled: true`. "
            "Without it they are left out, and no journey carries `cancelled`.",
        ),
    ] = None,
) -> Any:
    """The next journeys leaving from (or arriving at) one stop."""
    if over_the_limit(limit):
        return PlainTextResponse("Invalid value for Parameter `limit`.", status_code=400)

    # The documented /v1 contract: an id wins over a station name. The PHP
    # did the opposite, which silently queried another stop (OpendataCH/Transport#226).
    wanted = id if truthy(id) else station
    if not truthy(wanted):
        return PhpJson(content=fields.apply({"station": None, "stationboard": []}))

    found = await _station(pool, wanted)
    if found is None:
        return PhpJson(content=fields.apply({"station": None, "stationboard": []}))

    board_station = location(found["id"], found["name"], found["lat"], found["lon"])
    when = moment_of(date or datetime_).replace(second=0, microsecond=0)
    arrivals = type == "arrival"
    modes = _modes(as_list(parameter(request, "transportations")))
    count = _count(limit)

    marked = truthy(show_cancelled)
    rows = await _calls_at(pool, found["idx"], when, arrivals, modes, count, marked)
    journeys = await _journeys(pool, rows, board_station, arrivals)
    if marked:
        for line, row in zip(journeys, rows, strict=True):
            line["cancelled"] = bool(row["cancelled"])
    return PhpJson(content=fields.apply({"station": board_station, "stationboard": journeys}))


async def _station(pool: asyncpg.Pool, wanted: str) -> asyncpg.Record | None:
    """By number when it is one, else the best match by name."""
    if wanted.isdigit():
        rows = await db.fetch(pool, BY_ID, wanted)
        if rows:
            return rows[0]
    term = normalize(wanted)
    if not term:
        return None
    pattern = _like_escape(term)
    rows = await db.fetch(
        pool,
        BY_NAME.replace("SELECT id,", "SELECT idx, id,"),
        term,
        f"%{pattern}%",
        f"{pattern}%",
        f"% {pattern}%",
        1,
        wanted.strip().lower(),
    )
    return rows[0] if rows else None


async def _calls_at(
    pool: asyncpg.Pool,
    station_idx: int,
    when: datetime,
    arrivals: bool,
    modes: list[str] | None,
    count: int,
    marked: bool = False,
) -> list[asyncpg.Record]:
    platforms = [
        r["idx"]
        for r in await db.fetch(pool, "SELECT idx FROM gtfs.stops WHERE station = $1", station_idx)
    ]
    for horizon in HORIZONS:
        rows = await _calls_within(pool, platforms, when, arrivals, modes, count, horizon, marked)
        if len(rows) > count or horizon == HORIZONS[-1]:
            return _cut(rows, count)
    return []


async def _calls_within(
    pool: asyncpg.Pool,
    platforms: list[int],
    when: datetime,
    arrivals: bool,
    modes: list[str] | None,
    count: int,
    horizon: int,
    marked: bool = False,
) -> list[asyncpg.Record]:
    instant = int(when.timestamp())
    args: list[Any] = [platforms, modes, marked]
    halves = []
    # Yesterday's service day for the trips past midnight, tomorrow's for a
    # stop whose next departure is in the morning: the horizon reaches it.
    for offset in (-1, 0, 1):
        day = when.date() + timedelta(days=offset)
        base = int(service_day_start(day).timestamp())
        start = len(args) + 1
        args += [day, base, instant - base, instant - base + horizon]
        halves.append(
            HALF.format(
                p=start,
                p1=start + 1,
                p2=start + 2,
                p3=start + 3,
                time="arr_s" if arrivals else "dep_s",
                end="first_seq" if arrivals else "last_seq",
                flag="dropoff" if arrivals else "pickup",
                cancelled=CANCELLED.format(p=start),
            )
        )
    args.append(count + TIES)
    query = " UNION ALL ".join(f"({h})" for h in halves) + f" ORDER BY at LIMIT ${len(args)}"
    return await db.fetch(pool, query, *args)


def _cut(rows: list[asyncpg.Record], count: int) -> list[asyncpg.Record]:
    """`limit` rows, and every further one in the same minute as the last.

    search.ch answers that way and /v1 documents it: the limit is not a hard
    limit.
    """
    if len(rows) <= count:
        return rows
    last_minute = rows[count - 1]["at"] // 60
    kept = rows[:count]
    for row in rows[count:]:
        if row["at"] // 60 != last_minute:
            break
        kept.append(row)
    return kept


async def _journeys(
    pool: asyncpg.Pool, rows: list[asyncpg.Record], board_station: dict, arrivals: bool
) -> list[dict]:
    if not rows:
        return []
    trip_ids = list({r["trip"] for r in rows})
    days = list({r["day"] for r in rows})
    trips = {t["idx"]: t for t in await db.fetch(pool, TRIPS, trip_ids)}
    calls: dict[int, list[asyncpg.Record]] = {}
    for call in await db.fetch(pool, CALLS, trip_ids, days):
        calls.setdefault(call["trip"], []).append(call)

    # The railways' occupancy forecast, for the trains among them.
    forecast = await occupancy.by_train(
        pool,
        {
            (r["day"], trips[r["trip"]]["short_name"])
            for r in rows
            if trips[r["trip"]]["mode"] == "train" and trips[r["trip"]]["short_name"]
        },
    )

    now = datetime.now(ZURICH).replace(microsecond=0)
    journeys = []
    for row in rows:
        trip = trips[row["trip"]]
        levels = forecast.get((row["day"], trip["short_name"])) if trip["mode"] == "train" else None
        here = next(c for c in calls[row["trip"]] if c["seq"] == row["seq"])
        at = moment(row["day"], row["arr_s"] if arrivals else row["dep_s"])
        delay = here["arrival_delay"] if arrivals else here["departure_delay"]

        # /v1 reads the board's time into `departure` whichever way the board
        # faces. A train that ends here leaves with nobody.
        #
        # The PHP built the stop's `location`, and the head of the pass list,
        # with the terminal's id and no name (search.ch's `terminal.id`
        # overwrote the stop's own): the board stop's time and platform under
        # another stop's id (OpendataCH/Transport#175). Both are the board
        # stop now.
        leaving = occupancy.at(levels, here["id"]) if row["seq"] != trip["last_seq"] else None

        def head(_at=at, _delay=delay, _here=here, _leaving=leaving) -> dict:
            board_stop = stop(
                dict(board_station),
                None,
                _at,
                _here["platform"],
                _here["arrival_delay"],
                _delay,
                now,
            )
            set_capacity(board_stop, _leaving)
            return board_stop

        pass_list = [head()]
        for call in calls[row["trip"]]:
            if call["seq"] <= row["seq"]:
                continue
            place = location(call["id"], call["name"], call["lat"], call["lon"])
            last = call["seq"] == trip["last_seq"]
            checkpoint = stop(
                place,
                moment(row["day"], call["arr_s"]),
                None if last else moment(row["day"], call["dep_s"]),
                None,
                call["arrival_delay"],
                call["departure_delay"],
                now,
            )
            if not last:
                set_capacity(checkpoint, occupancy.at(levels, call["id"]))
            pass_list.append(checkpoint)

        line = journey(
            trip_short_name=trip["short_name"],
            route_short_name=trip["route_short_name"],
            category=trip["category"],
            operator=trip["operator"],
            headsign=trip["headsign"],
            pass_list=pass_list,
            trip=trip_ref(trip["trip_id"], row["day"]),
        )
        line["capacity1st"], line["capacity2nd"] = highest_capacity(pass_list)
        journeys.append({"stop": head(), **line})
    return journeys


def _modes(transportations: list[str]) -> list[str] | None:
    """The modes to keep, or None for all - `all` and unknown names included."""
    if not transportations or transportations[0] == "all":
        return None
    modes = []
    for name in transportations:
        mode = DEPRECATED_TYPES.get(name, name)
        if mode in TRANSPORTATIONS and mode not in modes:
            modes.append(mode)
    return modes or None


def _count(limit: str) -> int:
    try:
        return max(int(float(limit)), 1)
    except ValueError:
        return int(DEFAULT_LIMIT)


def over_the_limit(limit: str) -> bool:
    """`$limit > 420`, with PHP 8's comparison rules.

    A numeric string is compared as a number. A non-numeric one makes PHP cast
    the *number* to a string and compare the two as text - so `limit=abc` is
    "greater" than `420` and refused, while `limit=4abc` is not. Silly, and
    what the endpoint does.
    """
    try:
        return float(limit) > MAX_LIMIT
    except ValueError:
        return limit > str(MAX_LIMIT)


def moment_of(given: str | None) -> datetime:
    """The moment to ask about: what was given, or now, in Zurich."""
    now = datetime.now(ZURICH)
    if not given:
        return now
    parsed = phptime.parse(given, now, convert_offset=False)
    if parsed is not None:
        return parsed

    # /v1 lets the DateTime constructor throw here, which its error handler
    # turns into a 500 naming the string it could not read.
    raise errors.ApiError(500, f"DateTime::__construct(): Failed to parse time string ({given})")
