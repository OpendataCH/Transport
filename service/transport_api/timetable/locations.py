"""`/v2/locations` from the timetable database, in the shape of `/v1`.

Stations only: the GTFS feed has no addresses, so a search that search.ch
would answer with a street comes back without it.
"""

import math
from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, Query

from ..encoding import PhpJson
from ..fields import Fields
from ..models import Errors, LocationsResponse
from ..query import truthy
from . import db, places
from .mapping import location
from .names import normalize
from .router import Motis, motis_or_none

router = APIRouter()

LIMIT = 10
# Lines of an `all` answer kept for addresses and points of interest.
PLACES_AT_LEAST = 3

# The name exactly as typed first, punctuation included: «Winterthur, Seen»
# is the bus stop, «Winterthur Seen» the station, and the comma says which.
# Then the exact name after normalising. Then every name that contains the query, ranked by how
# busy it is - a match at the start of the name counting four times, one at the
# start of a later word once, one inside a word a fifth. That keeps Tesserete,
# Stazione above Lugano, Via Tesserete and Zürich, Bellevue above a quiet
# Bellevue GE, Ermitage, as search.ch ranks them, and a stop nothing calls at
# last. A train counts five times: a tram stop in Basel sees more departures
# than Basel SBB, and is not what "Basel" means. Names that merely resemble
# the query follow by trigram similarity, a Swiss stop before a foreign one.
BY_NAME = """
SELECT id, name, lat, lon, mode
FROM (SELECT *, departures * CASE mode WHEN 'train' THEN 5 ELSE 1 END AS weight
      FROM gtfs.station) station
WHERE name_norm LIKE $2 OR name_norm % $1
ORDER BY lower(name) = $6 DESC,
         name_norm = $1 DESC,
         CASE WHEN name_norm LIKE $3 THEN weight * 4.0
              WHEN name_norm LIKE $4 THEN weight * 1.0
              WHEN name_norm LIKE $2 THEN weight * 0.2
              ELSE 0 END DESC,
         id LIKE '85%' DESC,
         similarity(name_norm, $1) DESC,
         departures DESC
LIMIT $5
"""

# `pos` carries the longitude shrunk by cos(46.8°); see finish.sql.
NEAREST = """
SELECT id, name, lat, lon, mode
FROM gtfs.station
ORDER BY pos <-> point($2 * 0.6845, $1)
LIMIT $3
"""


@router.get(
    "/locations",
    summary="Search for stations",
    response_model=LocationsResponse,
    responses={503: {"model": Errors, "description": "The timetable is not loaded."}},
)
async def search_locations(
    pool: Annotated[asyncpg.Pool, Depends(db.get_pool)],
    motis: Annotated[Motis | None, Depends(motis_or_none)],
    fields: Annotated[Fields, Depends(Fields.of)],
    query: Annotated[str | None, Query(description="Station name to search for.")] = None,
    x: Annotated[str | None, Query(description="Latitude to search around.")] = None,
    y: Annotated[str | None, Query(description="Longitude to search around.")] = None,
    type: Annotated[  # noqa: A002 - the name is part of the /v1 contract
        str | None,
        Query(description="`all` (default), `station`, `poi` or `address`; with `query` only."),
    ] = None,
    fields_: Annotated[
        list[str] | None,
        Query(alias="fields[]", description="Keep only these parts of the answer."),
    ] = None,
) -> Any:
    """Stations by name, or the stations nearest a coordinate."""
    stations: list[dict] = []

    if truthy(query):
        stations = await _by_query(pool, motis, query, (type or "all").lower())
    elif truthy(x) and truthy(y):
        point = _point(x, y)
        if point is not None:
            stations = await _near(pool, motis, *point)

    return PhpJson(content=fields.apply({"stations": stations}))


async def _by_query(pool: asyncpg.Pool, motis: Motis | None, query: str, kind: str) -> list[dict]:
    """Stops, addresses or points of interest, as `type` asks.

    `all` gives stops first - they are what the API is for - followed by
    addresses and points of interest to fill the list. Those have no id,
    which is how a client tells them apart.
    """
    if kind in places.KINDS:
        return [_place(p) for p in await places.search(motis, query, (kind,), LIMIT)]
    stations = await _by_name(pool, query)
    if kind == "station":
        return stations
    # Places get the room the stops leave, and at least a few lines, so that
    # an address is found even when its street shares its name with stops.
    room = max(PLACES_AT_LEAST, LIMIT - len(stations))
    more = [_place(p) for p in await places.search(motis, query, ("address", "poi"), room)]
    return stations[: LIMIT - len(more)] + more


def _place(place: places.Place) -> dict:
    """An address or point of interest: no id, and `icon` null, as /v1 gives them."""
    return location(None, place.name, place.lat, place.lon, icon=None)


async def _by_name(pool: asyncpg.Pool, query: str) -> list[dict]:
    term = normalize(query)
    if not term:
        return []
    pattern = _like_escape(term)
    rows = await db.fetch(
        pool,
        BY_NAME,
        term,
        f"%{pattern}%",
        f"{pattern}%",
        f"% {pattern}%",
        LIMIT,
        query.strip().lower(),
    )
    return [location(r["id"], r["name"], r["lat"], r["lon"], icon=r["mode"]) for r in rows]


async def _near(pool: asyncpg.Pool, motis: Motis | None, lat: float, lon: float) -> list[dict]:
    """The nearest address first, then the nearest stops - as /v1 has answered.

    The address's distance has decimals and the stops' have none: that is
    how search.ch gives them.
    """
    stations = await _nearest(pool, lat, lon)
    address = await places.nearest_address(motis, lat, lon)
    if address is None:
        return stations
    metres = _exact_metres(lat, lon, address.lat, address.lon)
    if metres > places.NEAREST_ADDRESS_METRES:
        return stations
    first = location(None, address.name, address.lat, address.lon, distance=metres, icon=None)
    return [first, *stations[: LIMIT - 1]]


async def _nearest(pool: asyncpg.Pool, lat: float, lon: float) -> list[dict]:
    rows = await db.fetch(pool, NEAREST, lat, lon, LIMIT)
    return [
        location(
            r["id"],
            r["name"],
            r["lat"],
            r["lon"],
            distance=_metres(lat, lon, r["lat"], r["lon"]),
            icon=r["mode"],
        )
        for r in rows
    ]


def _point(x: str, y: str) -> tuple[float, float] | None:
    try:
        lat, lon = float(x), float(y)
    except ValueError:
        return None
    if not (math.isfinite(lat) and math.isfinite(lon)):
        return None
    return lat, lon


def _exact_metres(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres, with its decimals."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi, dlambda = phi2 - phi1, math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 6371000 * 2 * math.asin(math.sqrt(a))


def _metres(lat1: float, lon1: float, lat2: float | None, lon2: float | None) -> int | None:
    """Great-circle distance, whole metres - search.ch's distances are integers."""
    if lat2 is None or lon2 is None:
        return None
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return round(2 * 6371000 * math.asin(math.sqrt(a)))


def _like_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
