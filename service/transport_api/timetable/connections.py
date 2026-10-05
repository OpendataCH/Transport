"""`/v2/connections` from our own router, in the shape of `/v1`.

MOTIS (motis-project, MIT) runs beside this service on the same GTFS feed and
the same real time, and does the routing; this module asks it and writes the
answer the way `/v1` does. Stations are resolved, and lines described, from
the timetable database, so that a connection names its stops and its trains
exactly as the station board does.

Differences to /v1 that follow from the source: at most two `via` stops (what
MOTIS takes), no addresses, no pass-through points in a pass list.
"""

import re
from datetime import datetime
from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, Query, Request

from .. import settings
from ..connections import (
    DEFAULT_LIMIT,
    DEFAULT_PAGE,
    _is_arrival_time,
    _number,
    _page,
    _validate,
    _when,
)
from ..encoding import PhpErrorJson, PhpJson
from ..fields import Fields
from ..mapping import DEPRECATED_TYPES, ZURICH, duration_of
from ..models import ConnectionsResponse, Errors
from ..query import as_list, parameter, truthy
from . import db, places
from .mapping import journey, line_number, location, stop
from .names import normalize, operator_name
from .router import Motis, get_motis, motis_or_none  # noqa: F401 - re-exported
from .stationboard import TRANSPORTATIONS, _station

router = APIRouter()

# MOTIS prefixes every stop and trip id with the dataset's tag.
DATASET = "ch_"

MAX_VIA = 2

# /v1's means of transport, as MOTIS modes.
MODES = {
    "train": ["HIGHSPEED_RAIL", "LONG_DISTANCE", "NIGHT_RAIL", "REGIONAL_RAIL", "SUBURBAN"],
    "tram": ["TRAM", "SUBWAY"],
    "bus": ["BUS", "COACH"],
    "ship": ["FERRY"],
    "cableway": ["FUNICULAR", "AERIAL_LIFT"],
}

STATIONS = """
SELECT s.stop_id, st.id, st.name, st.lat, st.lon
FROM gtfs.stops s
JOIN gtfs.station st ON st.idx = s.station
WHERE s.stop_id = ANY($1::text[])
"""

TRIPS = """
SELECT t.trip_id, t.short_name, t.headsign, r.short_name AS route_short_name, r.category,
       a.name AS operator
FROM gtfs.trips t
JOIN gtfs.routes r ON r.idx = t.route
LEFT JOIN gtfs.agency a ON a.idx = r.agency
WHERE t.trip_id = ANY($1::text[])
"""

PARENT = "SELECT stop_id FROM gtfs.stops WHERE idx = $1"


@router.get(
    "/connections",
    summary="Search connections",
    response_model=ConnectionsResponse,
    responses={
        400: {"model": Errors, "description": "A parameter is out of range."},
        503: {"model": Errors, "description": "Timetable or router not available."},
    },
)
async def search_connections(
    request: Request,
    pool: Annotated[asyncpg.Pool, Depends(db.get_pool)],
    motis: Annotated[Motis, Depends(get_motis)],
    fields: Annotated[Fields, Depends(Fields.of)],
    from_: Annotated[
        str | None, Query(alias="from", description="Where the journey starts.")
    ] = None,
    to: Annotated[str | None, Query(description="Where it ends.")] = None,
    via: Annotated[
        list[str] | None, Query(alias="via[]", description="Up to two stops to pass through.")
    ] = None,
    date: Annotated[str | None, Query(description="Date of the journey, `YYYY-MM-DD`.")] = None,
    time: Annotated[str | None, Query(description="Time of the journey, `hh:mm`.")] = None,
    datetime_: Annotated[
        str | None, Query(alias="datetime", description="Date and time in one.")
    ] = None,
    isArrivalTime: Annotated[  # noqa: N803 - the name is part of the /v1 contract
        str | None, Query(description="`1` or `true` if the given time is the arrival time.")
    ] = None,
    limit: Annotated[str | None, Query(description="1 - 16; the default is 4.")] = None,
    page: Annotated[str | None, Query(description="0 - 10. Zero-based page.")] = None,
    transportations: Annotated[
        list[str] | None,
        Query(alias="transportations[]", description="Means of transport to allow."),
    ] = None,
    shared_mobility: Annotated[
        str | None,
        Query(
            alias="sharedMobility",
            description="`1` to allow shared bikes, scooters and cars (GBFS) to and from the "
            "stops, besides walking. Off by default.",
        ),
    ] = None,
    fields_: Annotated[
        list[str] | None,
        Query(alias="fields[]", description="Keep only these parts of the answer."),
    ] = None,
) -> Any:
    """The next connections from one stop to another."""
    empty = {"connections": [], "from": None, "to": None, "stations": {"from": [], "to": []}}
    if not (truthy(from_) and truthy(to)):
        return PhpJson(content=fields.apply(empty))

    places = as_list(parameter(request, "via"))
    limit_value = _number(limit, DEFAULT_LIMIT)
    page_value = _number(page, DEFAULT_PAGE)
    problems = _validate(limit_value, page_value, places)
    if len(places) > MAX_VIA:
        problems.append(f"Invalid via count (max {MAX_VIA} allowed on /v2).")
    if problems:
        return PhpErrorJson(status_code=400, content={"errors": problems})

    origin = await _endpoint(pool, motis, from_)
    destination = await _endpoint(pool, motis, to)
    stops_via = [await _station(pool, place) for place in places]
    if origin is None or destination is None or None in stops_via:
        return PhpJson(content=fields.apply(empty))

    arrival = _is_arrival_time(isArrivalTime)
    when = _when(datetime_, date, time)
    params = {
        "fromPlace": await _router_place(pool, origin),
        "toPlace": await _router_place(pool, destination),
        "time": when.astimezone(ZURICH).isoformat(),
        "arriveBy": "true" if arrival else "false",
        "numItineraries": str(limit_value if arrival else (page_value + 1) * limit_value),
        # Walking all the way is not a connection /v1 has ever offered.
        "directModes": "",
        "detailedTransfers": "false",
        "maxPreTransitTime": str(settings.MOTIS_MAX_WALK_SECONDS),
        "maxPostTransitTime": str(settings.MOTIS_MAX_WALK_SECONDS),
    }
    if truthy(shared_mobility) and shared_mobility.lower() not in ("0", "false"):
        # A shared vehicle may take the place of the walk to the first stop
        # and from the last; between stops it is still walking.
        params["preTransitModes"] = "WALK,RENTAL"
        params["postTransitModes"] = "WALK,RENTAL"
    if stops_via:
        params["via"] = ",".join([await _place(pool, s) for s in stops_via])
    modes = _modes(as_list(parameter(request, "transportations")))
    if modes:
        params["transitModes"] = ",".join(modes)

    if arrival:
        itineraries = await _arrival_page(motis, params, limit_value, page_value)
    else:
        plan = await motis.plan(params)
        itineraries = sorted(plan.get("itineraries") or [], key=lambda i: i["startTime"])
        itineraries = _page(itineraries, limit_value, page_value)
    _name_the_ends(itineraries, origin, destination)
    page_of = await _connections(pool, itineraries)

    origin_location = _endpoint_location(origin)
    # /v1 names the second of search.ch's points as `to`, and with a via stop
    # that is the first via, not the destination. Reproduced.
    second = stops_via[0] if stops_via else destination
    destination_location = _endpoint_location(second)
    return PhpJson(
        content=fields.apply(
            {
                "connections": page_of,
                "from": origin_location,
                "to": destination_location,
                "stations": {"from": [origin_location], "to": [destination_location]},
            }
        )
    )


async def _arrival_page(motis: "Motis", params: dict, limit: int, page: int) -> list[dict]:
    """The page /v1 shows for an arrival search.

    Page 0 is the `limit` connections that arrive last before the time asked
    for; page 1 is the next ones, arriving after it, and so on - read off the
    live /v1, which asks search.ch one page back. Later pages come from the
    router's own cursor to the next time window.
    """
    plan = await motis.plan(params)
    first = sorted(plan.get("itineraries") or [], key=lambda i: i["endTime"])
    if page == 0:
        return sorted(first[-limit:], key=lambda i: i["startTime"])
    later: list[dict] = []
    seen = {i["startTime"] + i["endTime"] for i in first}
    cursor = plan.get("nextPageCursor")
    for _ in range(page * 3):
        if len(later) >= page * limit or not cursor:
            break
        more = await motis.plan({**params, "pageCursor": cursor})
        for itinerary in sorted(more.get("itineraries") or [], key=lambda i: i["endTime"]):
            key = itinerary["startTime"] + itinerary["endTime"]
            if key not in seen:
                seen.add(key)
                later.append(itinerary)
        cursor = more.get("nextPageCursor")
    return sorted(later[(page - 1) * limit : page * limit], key=lambda i: i["startTime"])


async def _endpoint(
    pool: asyncpg.Pool, motis: Motis, text: str
) -> "asyncpg.Record | places.Place | None":
    """Where a connection starts or ends: a stop, an address or a point of interest.

    A text with a house number is tried as an address first - a stop of that
    name would be a coincidence, a street with that name a near certainty.
    Otherwise a stop, and an address or a point of interest when no stop
    matches.
    """
    station = await _station(pool, text)
    if text.isdigit() or (station is not None and normalize(station["name"]) == normalize(text)):
        return station
    found = await places.address(motis, text)
    if found is not None:
        return found
    if station is not None:
        return station
    matches = await places.search(motis, text, ("address", "poi"), limit=1)
    return matches[0] if matches else None


async def _router_place(pool: asyncpg.Pool, end) -> str:
    if isinstance(end, places.Place):
        return end.coordinate
    return await _place(pool, end)


def _endpoint_location(end) -> dict:
    if isinstance(end, places.Place):
        return location(None, end.name, end.lat, end.lon)
    return location(end["id"], end["name"], end["lat"], end["lon"])


def _name_the_ends(itineraries: list[dict], origin, destination) -> None:
    """The router calls a start or end that is no stop START or END; /v1 names it."""
    for itinerary in itineraries:
        legs = itinerary.get("legs") or []
        if not legs:
            continue
        if isinstance(origin, places.Place):
            legs[0]["from"]["name"] = origin.name
        if isinstance(destination, places.Place):
            legs[-1]["to"]["name"] = destination.name


async def _place(pool: asyncpg.Pool, station: asyncpg.Record) -> str:
    rows = await db.fetch(pool, PARENT, station["idx"])
    return DATASET + rows[0]["stop_id"]


async def _connections(pool: asyncpg.Pool, itineraries: list[dict]) -> list[dict]:
    if not itineraries:
        return []
    stop_ids, trip_ids = set(), set()
    for itinerary in itineraries:
        for leg in itinerary["legs"]:
            for place in [leg["from"], leg["to"], *(leg.get("intermediateStops") or [])]:
                stop_ids.add(_stop_id(place))
            if leg.get("tripId"):
                trip_ids.add(_trip_id(leg["tripId"]))
    stations = {r["stop_id"]: r for r in await db.fetch(pool, STATIONS, list(stop_ids))}
    trips = {r["trip_id"]: r for r in await db.fetch(pool, TRIPS, list(trip_ids))}
    now = datetime.now(ZURICH).replace(microsecond=0)
    return [_connection(i, stations, trips, now) for i in itineraries]


def _connection(itinerary: dict, stations: dict, trips: dict, now: datetime) -> dict:
    legs = [leg for leg in itinerary["legs"] if not _transfer_within_station(leg)]
    sections = [_section(leg, stations, trips, now) for leg in legs]
    first, last = legs[0], legs[-1]
    products = [
        _product(trips.get(_trip_id(leg["tripId"])) or _trip_of_leg(leg))
        for leg in legs
        if leg.get("tripId")
    ]
    destination = _stop(last["to"], stations, now, last.get("realTime"), arrives=True)
    if destination["platform"] is None:
        # /v1 copies search.ch's empty string for a stop without a platform.
        destination["platform"] = ""
    return {
        "from": _stop(first["from"], stations, now, first.get("realTime"), departs=True),
        "to": destination,
        "duration": duration_of(itinerary["duration"]),
        "transfers": itinerary.get("transfers", 0),
        "service": None,
        "products": products,
        "capacity1st": None,
        "capacity2nd": None,
        "sections": sections or None,
    }


def _transfer_within_station(leg: dict) -> bool:
    """A walk from one platform to another of the same station is no section in /v1."""
    return leg["mode"] == "WALK" and (leg["from"].get("parentId") or leg["from"].get("stopId")) == (
        leg["to"].get("parentId") or leg["to"].get("stopId")
    )


def _section(leg: dict, stations: dict, trips: dict, now: datetime) -> dict:
    live = leg.get("realTime")
    departure = _stop(leg["from"], stations, now, live, departs=True)
    arrival = _stop(leg["to"], stations, now, live, arrives=True)
    if not leg.get("tripId"):
        section = {
            "journey": None,
            # Seconds, as an integer: what /v1 passes on from search.ch.
            "walk": {"duration": int(leg.get("duration") or 0)},
            "departure": departure,
            "arrival": arrival,
        }
        if leg.get("mode") == "RENTAL":
            section["rental"] = _rental(leg.get("rental") or {})
        return section
    trip = trips.get(_trip_id(leg["tripId"])) or _trip_of_leg(leg)
    pass_list = [
        departure,
        *(
            _stop(p, stations, now, live, departs=True, arrives=True)
            for p in leg.get("intermediateStops") or []
        ),
        arrival,
    ]
    return {
        "journey": journey(
            trip_short_name=trip["short_name"],
            route_short_name=trip["route_short_name"],
            category=trip["category"],
            operator=trip["operator"],
            headsign=leg.get("headsign") or trip["headsign"],
            pass_list=pass_list,
        ),
        "walk": None,
        "departure": departure,
        "arrival": arrival,
    }


def _rental(rental: dict) -> dict:
    """What a shared vehicle is, in the words of GBFS, lower case."""

    def lower(value):
        return value.lower() if isinstance(value, str) else None

    return {
        # Some aggregated feeds name their system "Lime City partners from …".
        "provider": (rental.get("systemName") or rental.get("providerGroupId") or "").split(
            " from "
        )[0]
        or None,
        "vehicle": lower(rental.get("formFactor")),
        "propulsion": lower(rental.get("propulsionType")),
        "from_station": rental.get("fromStationName") or rental.get("stationName") or None,
        "to_station": rental.get("toStationName") or None,
        "url": rental.get("rentalUriWeb") or rental.get("url") or None,
    }


def _trip_of_leg(leg: dict) -> dict:
    """What the timetable would say about a trip it does not have.

    Real time adds trips - replacements, extras - that are in no GTFS file;
    the router knows them, the database does not. The category is the
    letters in front of the line (`IC81` -> `IC`).
    """
    route = leg.get("routeShortName")
    match = re.match(r"[A-Za-z]+", route or "")
    return {
        "short_name": leg.get("tripShortName"),
        "route_short_name": route,
        "category": match.group(0) if match else None,
        "operator": operator_name(
            (leg.get("agencyId") or "").removeprefix(DATASET), leg.get("agencyName")
        ),
        "headsign": leg.get("headsign"),
    }


def _stop(
    place: dict,
    stations: dict,
    now: datetime,
    live: bool | None,
    *,
    departs: bool = False,
    arrives: bool = False,
) -> dict:
    """A place of MOTIS as a /v1 stop: the station by its number, times in Zurich."""
    row = stations.get(_stop_id(place))
    if row is not None:
        station = location(row["id"], row["name"], row["lat"], row["lon"])
    else:
        station = location(None, place.get("name"), place.get("lat"), place.get("lon"))
    arrival = _time(place.get("scheduledArrival")) if arrives else None
    departure = _time(place.get("scheduledDeparture")) if departs else None
    return stop(
        station,
        arrival,
        departure,
        place.get("track") or place.get("scheduledTrack"),
        _delay(place.get("arrival"), place.get("scheduledArrival")) if live and arrives else None,
        _delay(place.get("departure"), place.get("scheduledDeparture"))
        if live and departs
        else None,
        now,
    )


def _stop_id(place: dict) -> str:
    """The station's stop id without the dataset tag - the parent's when there is one."""
    return (place.get("parentId") or place.get("stopId") or "").removeprefix(DATASET)


def _trip_id(motis_trip_id: str) -> str:
    """`20261006_07:59_ch_.ojp-91-81-A...` -> `.ojp-91-81-A...`."""
    _, _, rest = motis_trip_id.partition("_" + DATASET)
    return rest or motis_trip_id


def _time(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(ZURICH)


def _delay(actual: str | None, scheduled: str | None) -> int | None:
    """Whole minutes, seconds cut off - as the station board counts them.

    Called only for a leg the router has real time for; without it MOTIS
    repeats the scheduled time, and a zero would claim knowledge.
    """
    if not actual or not scheduled:
        return None
    seconds = int((_time(actual) - _time(scheduled)).total_seconds())
    minutes = abs(seconds) // 60
    return minutes if seconds >= 0 else -minutes


# Categories search.ch writes with a space before the line: `IC 5`, `IR 13`.
SPACED = {"IC", "ICN", "IR", "IRE", "EC", "EN"}


def _product(trip) -> str:
    """The line as search.ch names it in `products`, read off /v1's answers.

    `IC 5` and `IR 13` with a space; `S29`, `RE37`, `EV2` without; a train
    without a line (`ICE`, `TER`) and any regional train (`R`) by its
    category alone; buses, trams and boats by their number only (`21`).
    """
    category, route = trip["category"], trip["route_short_name"]
    if not category:
        return route or ""
    if not route or route == category or category == "R":
        return category
    number = line_number(route, category, None)
    if category in SPACED:
        return f"{category} {number}"
    if route.startswith(category):
        return route
    return number


def _modes(transportations: list[str]) -> list[str] | None:
    if not transportations or transportations[0] == "all":
        return None
    modes: list[str] = []
    for name in transportations:
        kind = DEPRECATED_TYPES.get(name, name)
        if kind in TRANSPORTATIONS:
            modes += [m for m in MODES[kind] if m not in modes]
    return modes or None
