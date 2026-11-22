"""`/v2/map/*`: what the map example draws, from the timetable and the router.

Not part of the /v1 contract, and shaped for a map rather than for
compatibility: every station with its position, the vehicles under way in a
box, the stops reachable from a point within some minutes, and the run of one
trip. The router's answers are cached briefly per question, so that a map
left open in many browsers asks the router no more than a few at a time.
"""

import re
import time
from datetime import UTC, datetime, timedelta
from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from .. import errors
from . import db
from .connections import Motis, get_motis
from .connections import _place as router_place
from .router import plan_slot

router = APIRouter(prefix="/map", tags=["map"])

# The station nearest a point that has departures, for a start the router
# cannot reach on foot (a router without a street network).
NEAREST_SERVED = """
SELECT idx, id, name, lat, lon FROM gtfs.station
WHERE departures > 0
ORDER BY pos <-> point($2 * 0.6845, $1)
LIMIT 1
"""

STATIONS = """
SELECT id, name, lat, lon, mode, departures FROM gtfs.station
WHERE departures > 0 ORDER BY departures DESC
"""

# How long an answer is kept, per kind of question.
STATIONS_SECONDS = 3600
VEHICLES_SECONDS = 15
REACHABLE_SECONDS = 120
TRIP_SECONDS = 30

# The vehicles of a box larger than this (in degrees, about 110 km by 75 km)
# would be most of the country: the map asks for them only when zoomed in.
MAX_BOX = 1.0

# Answers already given: key -> (expires at, value).
_cache: dict[tuple, tuple[float, Any]] = {}


async def _cached(key: tuple, seconds: int, produce) -> Any:
    now = time.monotonic()
    hit = _cache.get(key)
    if hit and hit[0] > now:
        return hit[1]
    value = await produce()
    if len(_cache) > 2000:
        for stale in [k for k, (until, _) in _cache.items() if until <= now]:
            del _cache[stale]
    _cache[key] = (now + seconds, value)
    return value


def _cacheable(content: Any, seconds: int) -> JSONResponse:
    return JSONResponse(content, headers={"Cache-Control": f"public, max-age={seconds}"})


def _coordinate(value: str, name: str) -> tuple[float, float]:
    try:
        lat, lon = (float(part) for part in value.split(","))
    except ValueError:
        raise errors.ApiError(400, f"`{name}` is `latitude,longitude`.") from None
    return lat, lon


# A Swiss stop's SLOID carries its DiDok number: `ch:1:sloid:3000` (and its
# platforms, and the parent `Parentch:1:sloid:3000`) is station 8503000.
SLOID = re.compile(r"^(?:Parent)?ch:1:sloid:(\d+)")


def _station_id(stop_id: str | None) -> str | None:
    """The station id /v1 uses, from the router's stop id."""
    if not stop_id:
        return None
    if stop_id.startswith("ch_"):
        stop_id = stop_id[3:]
    match = SLOID.match(stop_id)
    if match:
        return "85" + match.group(1).zfill(5)
    return stop_id.split(":")[0]


@router.get("/stations", summary="Every served station with its position")
async def stations(pool: Annotated[asyncpg.Pool, Depends(db.get_pool)]) -> JSONResponse:
    """`[id, name, latitude, longitude, mode, departures a day]`, busiest first."""

    async def produce():
        rows = await db.fetch(pool, STATIONS)
        return {
            "fields": ["id", "name", "lat", "lon", "mode", "departures"],
            "stations": [
                [
                    r["id"],
                    r["name"],
                    round(r["lat"], 6),
                    round(r["lon"], 6),
                    r["mode"],
                    r["departures"],
                ]
                for r in rows
            ],
        }

    return _cacheable(await _cached(("stations",), STATIONS_SECONDS, produce), STATIONS_SECONDS)


async def _one_to_all(motis: Motis, params: dict[str, str]) -> dict:
    """Everything reachable is a search, and waits for a slot like one."""
    async with plan_slot():
        return await motis.get("/api/v6/one-to-all", params)


@router.get("/vehicles", summary="Vehicles under way in a box, now")
async def vehicles(
    motis: Annotated[Motis, Depends(get_motis)],
    min: Annotated[str, Query(description="South-west corner, `latitude,longitude`.")],  # noqa: A002
    max: Annotated[str, Query(description="North-east corner, `latitude,longitude`.")],  # noqa: A002
    zoom: Annotated[int, Query(ge=0, le=22)] = 12,
) -> JSONResponse:
    """The segments vehicles travel in the next minutes, with their times.

    Each segment runs from one stop to the next; a client places the vehicle
    on it by the time. The box is rounded outwards to a hundredth of a degree,
    so that maps scrolled a little share an answer.
    """
    south, west = _coordinate(min, "min")
    north, east = _coordinate(max, "max")
    if north - south > MAX_BOX or east - west > MAX_BOX:
        raise errors.ApiError(400, "The box is too large; zoom in.")
    south, west = int(south * 100) / 100, int(west * 100) / 100
    north, east = int(north * 100 + 1) / 100, int(east * 100 + 1) / 100
    now = datetime.now(UTC).replace(second=0, microsecond=0)

    async def produce():
        segments = await motis.get(
            "/api/v6/map/trips",
            {
                "min": f"{south},{west}",
                "max": f"{north},{east}",
                "zoom": str(zoom),
                "startTime": now.isoformat().replace("+00:00", "Z"),
                "endTime": (now + timedelta(minutes=3)).isoformat().replace("+00:00", "Z"),
            },
        )
        return {
            "segments": [
                {
                    "trip": (s.get("trips") or [{}])[0].get("tripId"),
                    "name": (s.get("trips") or [{}])[0].get("displayName"),
                    "mode": s.get("mode"),
                    "from": _place(s.get("from")),
                    "to": _place(s.get("to")),
                    "departure": s.get("departure"),
                    "arrival": s.get("arrival"),
                    "delay": _delay(s.get("scheduledDeparture"), s.get("departure")),
                    "realTime": s.get("realTime"),
                    "polyline": s.get("polyline"),
                }
                for s in segments
            ]
        }

    key = ("vehicles", south, west, north, east, zoom, now)
    return _cacheable(await _cached(key, VEHICLES_SECONDS, produce), VEHICLES_SECONDS)


@router.get("/reachable", summary="Stops reachable from a point within some minutes")
async def reachable(
    motis: Annotated[Motis, Depends(get_motis)],
    pool: Annotated[asyncpg.Pool, Depends(db.get_pool)],
    x: Annotated[float, Query(description="Latitude of the start.")],
    y: Annotated[float, Query(description="Longitude of the start.")],
    minutes: Annotated[int, Query(ge=5, le=180)] = 60,
    time_: Annotated[
        str | None, Query(alias="time", description="ISO time; now by default.")
    ] = None,
) -> JSONResponse:
    """Each stop once, with the shortest travel time and the transfers it takes."""
    x, y = round(x, 4), round(y, 4)

    async def produce():
        params = {"one": f"{x},{y}", "maxTravelTime": str(minutes)}
        if time_:
            params["time"] = time_
        answer = await _one_to_all(motis, params)
        start = None
        if not answer.get("all"):
            # Nothing on foot from the point: start at the nearest station.
            rows = await db.fetch(pool, NEAREST_SERVED, x, y)
            if rows:
                start = rows[0]
                params["one"] = await router_place(pool, start)
                answer = await _one_to_all(motis, params)
        best: dict[str, dict] = {}
        for item in answer.get("all", []):
            place = item.get("place") or {}
            key = _station_id(place.get("parentId") or place.get("stopId")) or place.get("name")
            duration = item.get("duration")
            if key is None or duration is None:
                continue
            if key not in best or duration < best[key]["minutes"]:
                best[key] = {
                    "id": key,
                    "name": place.get("name"),
                    "lat": place.get("lat"),
                    "lon": place.get("lon"),
                    "minutes": duration,
                    "transfers": item.get("k"),
                }
        origin = {"lat": x, "lon": y}
        if start is not None:
            origin = {key: start[key] for key in ("lat", "lon", "id", "name")}
        return {"from": origin, "minutes": minutes, "stops": list(best.values())}

    key = ("reachable", x, y, minutes, time_ or int(time.time() // REACHABLE_SECONDS))
    return _cacheable(await _cached(key, REACHABLE_SECONDS, produce), REACHABLE_SECONDS)


@router.get("/trip", summary="The run of one trip, with real time")
async def trip(
    motis: Annotated[Motis, Depends(get_motis)],
    id: Annotated[str, Query(description="A trip id as `/map/vehicles` names it.")],  # noqa: A002
) -> JSONResponse:
    """Its stops in order, with planned and expected times and tracks."""

    async def produce():
        answer = await motis.get("/api/v6/trip", {"tripId": id})
        legs = answer.get("legs") or []
        if not legs:
            raise errors.ApiError(404, "No such trip.")
        leg = legs[0]
        stops = [leg.get("from"), *(leg.get("intermediateStops") or []), leg.get("to")]
        return {
            "name": leg.get("displayName") or leg.get("routeShortName"),
            "headsign": leg.get("headsign"),
            "operator": leg.get("agencyName"),
            "mode": leg.get("mode"),
            "realTime": leg.get("realTime"),
            "polyline": (leg.get("legGeometry") or {}).get("points"),
            "stops": [
                {
                    **_place(s),
                    "arrival": s.get("arrival"),
                    "departure": s.get("departure"),
                    "scheduledArrival": s.get("scheduledArrival"),
                    "scheduledDeparture": s.get("scheduledDeparture"),
                    "track": s.get("track") or s.get("scheduledTrack"),
                    "cancelled": s.get("cancelled"),
                }
                for s in stops
                if s
            ],
        }

    return _cacheable(await _cached(("trip", id), TRIP_SECONDS, produce), TRIP_SECONDS)


def _place(place: dict | None) -> dict:
    place = place or {}
    return {
        "id": _station_id(place.get("parentId") or place.get("stopId")),
        "name": place.get("name"),
        "lat": place.get("lat"),
        "lon": place.get("lon"),
    }


def _delay(scheduled: str | None, expected: str | None) -> int | None:
    """Whole minutes late, as /v1 counts them; None without both times."""
    if not scheduled or not expected:
        return None
    a = datetime.fromisoformat(scheduled.replace("Z", "+00:00"))
    b = datetime.fromisoformat(expected.replace("Z", "+00:00"))
    return int((b - a).total_seconds() // 60)
