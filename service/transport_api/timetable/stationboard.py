"""`/v2/stationboard` from the timetable database, in the shape of `/v1`.

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

from ..encoding import PhpJson
from ..fields import Fields
from ..mapping import DEPRECATED_TYPES, ZURICH
from ..models import Errors, StationBoardResponse
from ..query import as_list, parameter, truthy
from ..stationboard import DEFAULT_LIMIT, moment_of, over_the_limit
from . import db
from .locations import BY_NAME, _like_escape
from .mapping import journey, location, moment, service_day_start, stop
from .names import normalize

router = APIRouter()

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
HALF = """
SELECT st.trip, st.seq, st.stop, st.arr_s, st.dep_s, ${p}::date AS day,
       ${p1}::bigint + st.{time} AS at
FROM gtfs.stop_times st
JOIN gtfs.trips t ON t.idx = st.trip
JOIN gtfs.service_dates sd ON sd.service = t.service AND sd.day = ${p}::date
WHERE st.stop = ANY($1::int[])
  AND st.{time} >= ${p2} AND st.{time} < ${p3}
  AND st.seq <> t.{end}
  AND st.{flag} <> 1
  AND ($2::text[] IS NULL OR t.mode = ANY($2::text[]))
  AND NOT EXISTS (
      SELECT 1 FROM rt.trip_cancelled c
      WHERE c.trip_id = t.trip_id AND c.day = ${p}::date)
"""

TRIPS = """
SELECT t.idx, t.headsign, t.short_name, t.last_seq,
       r.short_name AS route_short_name, r.category, a.name AS operator,
       term.id AS terminal_id
FROM gtfs.trips t
JOIN gtfs.routes r ON r.idx = t.route
LEFT JOIN gtfs.agency a ON a.idx = r.agency
JOIN gtfs.stops ls ON ls.idx = t.last_stop
JOIN gtfs.station term ON term.idx = ls.station
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
        str | None, Query(description="The stop id, as an alternative to `station`.")
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
) -> Any:
    """The next journeys leaving from (or arriving at) one stop."""
    if over_the_limit(limit):
        return PlainTextResponse("Invalid value for Parameter `limit`.", status_code=400)

    wanted = station if truthy(station) else id
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

    rows = await _calls_at(pool, found["idx"], when, arrivals, modes, count)
    journeys = await _journeys(pool, rows, board_station, arrivals)
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
) -> list[asyncpg.Record]:
    platforms = [
        r["idx"]
        for r in await db.fetch(pool, "SELECT idx FROM gtfs.stops WHERE station = $1", station_idx)
    ]
    for horizon in HORIZONS:
        rows = await _calls_within(pool, platforms, when, arrivals, modes, count, horizon)
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
) -> list[asyncpg.Record]:
    instant = int(when.timestamp())
    args: list[Any] = [platforms, modes]
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

    now = datetime.now(ZURICH).replace(microsecond=0)
    journeys = []
    for row in rows:
        trip = trips[row["trip"]]
        here = next(c for c in calls[row["trip"]] if c["seq"] == row["seq"])
        terminal = location(trip["terminal_id"], None, None, None)
        at = moment(row["day"], row["arr_s"] if arrivals else row["dep_s"])
        delay = here["arrival_delay"] if arrivals else here["departure_delay"]

        # /v1 reads the board's time into `departure` whichever way the board
        # faces, and builds the head stop's station from the terminal.
        def head(station: dict, _at=at, _delay=delay, _here=here, _terminal=terminal) -> dict:
            return stop(
                station,
                None,
                _at,
                _here["platform"],
                _here["arrival_delay"],
                _delay,
                now,
                location_=dict(_terminal),
            )

        pass_list = [head(dict(terminal))]
        for call in calls[row["trip"]]:
            if call["seq"] <= row["seq"]:
                continue
            place = location(call["id"], call["name"], call["lat"], call["lon"])
            pass_list.append(
                stop(
                    place,
                    moment(row["day"], call["arr_s"]),
                    None if call["seq"] == trip["last_seq"] else moment(row["day"], call["dep_s"]),
                    None,
                    call["arrival_delay"],
                    call["departure_delay"],
                    now,
                )
            )

        journeys.append(
            {
                "stop": head(board_station),
                **journey(
                    trip_short_name=trip["short_name"],
                    route_short_name=trip["route_short_name"],
                    category=trip["category"],
                    operator=trip["operator"],
                    headsign=trip["headsign"],
                    pass_list=pass_list,
                ),
            }
        )
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
