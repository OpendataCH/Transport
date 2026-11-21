"""`/v1/trip`: one trip with all its stops, by its id or by its number.

A station board and a connection name each trip they show in `trip` (the
GTFS `trip_id` and the service day); this route gives the whole run - every
stop with its platform, times and real-time delays, as the station board
reads them from `rt.stop_delay`. The same `trip_id` and day are what a
GTFS-RT feed refers to.

A trip only real time knows (a replacement, an extra) has a `trip_id` that
no GTFS file has: the router knows it, the database does not, and this route
finds nothing for it.
"""

from datetime import date as Date  # noqa: N812 - `date` is a parameter here
from datetime import datetime
from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, Query

from .. import errors
from ..encoding import PhpJson
from ..fields import Fields
from ..mapping import ZURICH
from ..models import Errors, TripResponse
from ..query import truthy
from . import db, occupancy
from .mapping import highest_capacity, journey, location, moment, set_capacity, stop, trip_ref
from .stationboard import CALLS

router = APIRouter()

# Trips that share a number on one day: a train number is unique per
# operator, a bus's "number" is often its line's run and repeats.
MAX_TRIPS = 20

TRIP = """
SELECT t.idx, t.trip_id, t.headsign, t.short_name, t.mode, t.first_seq, t.last_seq,
       r.short_name AS route_short_name, r.category, a.name AS operator,
       EXISTS (SELECT 1 FROM rt.trip_cancelled c
               WHERE c.trip_id = t.trip_id AND c.day = $2) AS cancelled
FROM gtfs.trips t
JOIN gtfs.routes r ON r.idx = t.route
LEFT JOIN gtfs.agency a ON a.idx = r.agency
WHERE {where}
  AND EXISTS (SELECT 1 FROM gtfs.service_dates sd
              WHERE sd.service = t.service AND sd.day = $2)
ORDER BY t.mode = 'train' DESC, t.trip_id
LIMIT {limit}
"""

BY_ID = TRIP.format(where="t.trip_id = $1", limit=1)
# search.ch and /v1 write a train number six digits wide (`000707`).
BY_NUMBER = TRIP.format(where="ltrim(t.short_name, '0') = ltrim($1, '0')", limit=MAX_TRIPS)


@router.get(
    "/trip",
    summary="Get one trip with all its stops",
    response_model=TripResponse,
    responses={
        400: {"model": Errors, "description": "Neither `id` nor `number`, or a bad `date`."},
        503: {"model": Errors, "description": "The timetable is not loaded."},
    },
)
async def get_trip(
    pool: Annotated[asyncpg.Pool, Depends(db.get_pool)],
    fields: Annotated[Fields, Depends(Fields.of)],
    id: Annotated[  # noqa: A002 - named as in the other routes
        str | None,
        Query(description="The trip's id, as `trip.id` of a station board or connection gives it."),
    ] = None,
    number: Annotated[
        str | None,
        Query(description="The train number instead (`707`, or `000707` as `name` gives it)."),
    ] = None,
    date: Annotated[
        str | None,
        Query(description="The service day, `YYYY-MM-DD`; today by default."),
    ] = None,
    fields_: Annotated[
        list[str] | None,
        Query(alias="fields[]", description="Keep only these parts of the answer."),
    ] = None,
) -> Any:
    """Every stop of one trip, with platforms and real time."""
    day = _day(date)
    if truthy(id):
        rows = await db.fetch(pool, BY_ID, id, day)
    elif truthy(number):
        rows = await db.fetch(pool, BY_NUMBER, number.strip(), day)
    else:
        raise errors.ApiError(400, "Argument `id` or `number` is required.")
    return PhpJson(content=fields.apply({"trips": await _trips(pool, rows, day)}))


def _day(given: str | None) -> Date:
    if not truthy(given):
        return datetime.now(ZURICH).date()
    try:
        return Date.fromisoformat(given.strip())
    except ValueError:
        raise errors.ApiError(400, "Argument `date` must be `YYYY-MM-DD`.") from None


async def _trips(pool: asyncpg.Pool, rows: list[asyncpg.Record], day: Date) -> list[dict]:
    if not rows:
        return []
    calls: dict[int, list[asyncpg.Record]] = {}
    for call in await db.fetch(pool, CALLS, [r["idx"] for r in rows], [day]):
        calls.setdefault(call["trip"], []).append(call)
    forecast = await occupancy.by_train(
        pool, {(day, r["short_name"]) for r in rows if r["mode"] == "train" and r["short_name"]}
    )
    now = datetime.now(ZURICH).replace(microsecond=0)
    trips = []
    for row in rows:
        levels = forecast.get((day, row["short_name"])) if row["mode"] == "train" else None
        pass_list = []
        for call in calls.get(row["idx"], []):
            first, last = call["seq"] == row["first_seq"], call["seq"] == row["last_seq"]
            checkpoint = stop(
                location(call["id"], call["name"], call["lat"], call["lon"]),
                None if first else moment(day, call["arr_s"]),
                None if last else moment(day, call["dep_s"]),
                call["platform"],
                None if first else call["arrival_delay"],
                None if last else call["departure_delay"],
                now,
            )
            if not last:
                set_capacity(checkpoint, occupancy.at(levels, call["id"]))
            pass_list.append(checkpoint)
        line = journey(
            trip_short_name=row["short_name"],
            route_short_name=row["route_short_name"],
            category=row["category"],
            operator=row["operator"],
            headsign=row["headsign"],
            pass_list=pass_list,
            trip=trip_ref(row["trip_id"], day),
        )
        line["capacity1st"], line["capacity2nd"] = highest_capacity(pass_list)
        trips.append({**line, "cancelled": bool(row["cancelled"])})
    return trips
