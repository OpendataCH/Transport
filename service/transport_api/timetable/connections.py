"""`/v1/connections` (and `/v2`) from our own router.

MOTIS (motis-project, MIT) runs beside this service on the same GTFS feed and
the same real time, and does the routing; this module asks it and writes the
answer the way `/v1` does. Stations are resolved, and lines described, from
the timetable database, so that a connection names its stops and its trains
exactly as the station board does.

Differences to what /v1 answered from search.ch that follow from the source:
at most two `via` stops (what MOTIS takes), no pass-through points in a pass
list.
"""

import re
from datetime import date, datetime
from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, Query, Request

from .. import phptime, settings
from ..encoding import PhpErrorJson, PhpJson
from ..fields import Fields
from ..mapping import DEPRECATED_TYPES, ZURICH, duration_of
from ..models import ConnectionsResponse, Errors
from ..query import as_list, parameter, truthy
from . import db, occupancy, places
from .locations import _exact_metres
from .mapping import (
    highest_capacity,
    journey,
    line_number,
    location,
    set_capacity,
    stop,
    trip_ref,
)
from .names import normalize, operator_name
from .router import Motis, get_motis, motis_or_none  # noqa: F401 - re-exported
from .stationboard import TRANSPORTATIONS, _station

router = APIRouter()

# MOTIS prefixes every stop and trip id with the dataset's tag.
DATASET = "ch_"

DEFAULT_LIMIT = 4
DEFAULT_PAGE = 0

MAX_LIMIT = 16
MAX_PAGE = 10
# Earlier connections: page -1 is the `limit` connections before page 0.
MIN_PAGE = -10
# What MOTIS takes. search.ch took five.
MAX_VIA = 2

# A page is cut out of the first sixteen connections, as /v1 always has.
WINDOW = 16

# `walkingSpeed`, km/h, on the way to the first stop and from the last.
MIN_WALKING_SPEED = 2.0
MAX_WALKING_SPEED = 10.0
# `minTransferTime`, minutes: no change of vehicle is shorter.
MAX_TRANSFER_MINUTES = 60

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
       a.name AS operator, t.mode
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
    page: Annotated[
        str | None,
        Query(
            description="0 - 10. Zero-based page. -1 to -10 for the connections before "
            "the time asked for: -1 is the ones just before page 0."
        ),
    ] = None,
    walking_speed: Annotated[
        str | None,
        Query(
            alias="walkingSpeed",
            description="km/h, 2 - 10, on the way from an address or a coordinate to the "
            "first stop and from the last stop to one. The default is 5. Walks between stops "
            "are the timetable's.",
        ),
    ] = None,
    min_transfer_time: Annotated[
        str | None,
        Query(
            alias="minTransferTime",
            description="Minutes, 0 - 60: no change of vehicle shorter than this, even where "
            "the timetable allows one.",
        ),
    ] = None,
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
    geometry: Annotated[
        str | None,
        Query(
            description="`1` to give each section the line it follows on a map, as an encoded "
            "polyline (`geometry`). Off by default.",
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

    via_names = as_list(parameter(request, "via"))
    limit_value = _number(limit, DEFAULT_LIMIT)
    page_value = _number(page, DEFAULT_PAGE)
    problems = _validate(limit_value, page_value, via_names)
    speed = _decimal(walking_speed)
    if truthy(walking_speed) and (
        speed is None or not MIN_WALKING_SPEED <= speed <= MAX_WALKING_SPEED
    ):
        problems.append(
            f"Argument `walkingSpeed` must be between {MIN_WALKING_SPEED:g} "
            f"and {MAX_WALKING_SPEED:g} (km/h)."
        )
    transfer = _decimal(min_transfer_time)
    if truthy(min_transfer_time) and (
        transfer is None or not 0 <= transfer <= MAX_TRANSFER_MINUTES
    ):
        problems.append(
            f"Argument `minTransferTime` must be between 0 and {MAX_TRANSFER_MINUTES} (minutes)."
        )
    if problems:
        return PhpErrorJson(status_code=400, content={"errors": problems})

    origin = await _endpoint(pool, motis, from_)
    destination = await _endpoint(pool, motis, to)
    stops_via = [await _station(pool, place) for place in via_names]
    if origin is None or destination is None or None in stops_via:
        return PhpJson(content=fields.apply(empty))

    arrival = _is_arrival_time(isArrivalTime)
    when = _when(datetime_, date, time)
    params = {
        "fromPlace": await _router_place(pool, origin),
        "toPlace": await _router_place(pool, destination),
        "time": when.astimezone(ZURICH).isoformat(),
        "arriveBy": "true" if arrival else "false",
        "numItineraries": str(
            limit_value if arrival or page_value < 0 else (page_value + 1) * limit_value
        ),
        # Walking all the way is not a connection /v1 has ever offered.
        "directModes": "",
        "detailedTransfers": "false",
        "maxPreTransitTime": str(settings.MOTIS_MAX_WALK_SECONDS),
        "maxPostTransitTime": str(settings.MOTIS_MAX_WALK_SECONDS),
        "pedestrianSpeed": settings.MOTIS_PEDESTRIAN_SPEED
        if speed is None
        else f"{speed / 3.6:.3f}",
    }
    if transfer is not None:
        params["minTransferTime"] = str(int(transfer))
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

    itineraries = await _itineraries(motis, params, arrival, limit_value, page_value)
    if (
        not itineraries
        and page_value == 0
        and (isinstance(origin, places.Place) or isinstance(destination, places.Place))
    ):
        # An address far from any stop: walk further, and on foot all the
        # way when that is the only way (OpendataCH/Transport#206).
        itineraries = await _far_walk(motis, params, arrival, limit_value)
    _name_the_ends(itineraries, origin, destination)
    with_geometry = truthy(geometry) and geometry.lower() not in ("0", "false")
    page_of = await _connections(pool, itineraries, with_geometry)

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


async def _itineraries(
    motis: "Motis", params: dict, arrival: bool, limit: int, page: int
) -> list[dict]:
    """The page of connections asked for, in the order they leave."""
    if page < 0:
        return await _earlier_page(motis, params, arrival, limit, page)
    if arrival:
        return await _arrival_page(motis, params, limit, page)
    plan = await motis.plan(params)
    itineraries = sorted(plan.get("itineraries") or [], key=lambda i: i["startTime"])
    return _page(itineraries, limit, page)


async def _far_walk(motis: "Motis", params: dict, arrival: bool, limit: int) -> list[dict]:
    """Connections with a walk of up to an hour to the first stop or from the last.

    Without any, the walk itself - from a remote address to the next village
    walking is the connection - when it takes no longer than that either. Not
    with a via: the router's direct walk does not pass it.
    """
    seconds = str(settings.MOTIS_MAX_FAR_WALK_SECONDS)
    far = {
        **params,
        "maxPreTransitTime": seconds,
        "maxPostTransitTime": seconds,
        "directModes": "WALK",
        "maxDirectTime": seconds,
        "numItineraries": str(limit),
    }
    plan = await motis.plan(far)
    key = "endTime" if arrival else "startTime"
    found = sorted(plan.get("itineraries") or [], key=lambda i: i[key])
    found = found[-limit:] if arrival else found[:limit]
    if not found and "via" not in params:
        found = (plan.get("direct") or [])[:1]
    return sorted(found, key=lambda i: i["startTime"])


async def _earlier_page(
    motis: "Motis", params: dict, arrival: bool, limit: int, page: int
) -> list[dict]:
    """Page -1, -2, ...: the connections before page 0, going back in time.

    The router's cursor to the previous time window is followed until there
    are enough. For a departure, page 0 begins at the time asked for; for an
    arrival it is the connections arriving last before it, and what the first
    window has before those belongs to page -1.
    """
    key = "endTime" if arrival else "startTime"
    plan = await motis.plan(params)
    first = sorted(plan.get("itineraries") or [], key=lambda i: i[key])
    seen = {i["startTime"] + i["endTime"] for i in first}
    earlier = first[:-limit] if arrival else []
    wanted = -page * limit
    cursor = plan.get("previousPageCursor")
    for _ in range(-page * 3):
        if len(earlier) >= wanted or not cursor:
            break
        more = await motis.plan({**params, "pageCursor": cursor})
        for itinerary in more.get("itineraries") or []:
            mark = itinerary["startTime"] + itinerary["endTime"]
            if mark not in seen:
                seen.add(mark)
                earlier.append(itinerary)
        cursor = more.get("previousPageCursor")
    latest_first = sorted(earlier, key=lambda i: i[key], reverse=True)
    chosen = latest_first[(-page - 1) * limit : -page * limit]
    return sorted(chosen, key=lambda i: i["startTime"])


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
    """Where a connection starts or ends: a coordinate, a stop, an address or
    a point of interest.

    A coordinate is taken as it stands; the router walks from it to the stops
    nearby. A text with a house number is tried as an address first - a stop of that
    name would be a coincidence, a street with that name a near certainty.
    Otherwise a stop, and an address or a point of interest when no stop
    matches.
    """
    coordinate = places.point(text)
    if coordinate is not None:
        return await _at(motis, *coordinate)
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


async def _at(motis: Motis, lat: float, lon: float) -> places.Place:
    """A coordinate as a place: where it is, named after the address there.

    The connection starts at the point asked for, not at the address; without
    an address nearby the name is the coordinate itself.
    """
    name = f"{lat},{lon}"
    address = await places.nearest_address(motis, lat, lon)
    if address is not None and (
        _exact_metres(lat, lon, address.lat, address.lon) <= places.NEAREST_ADDRESS_METRES
    ):
        name = address.name
    return places.Place(name=name, lat=lat, lon=lon, kind="address")


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


async def _connections(
    pool: asyncpg.Pool, itineraries: list[dict], with_geometry: bool = False
) -> list[dict]:
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
    forecast = await occupancy.by_train(
        pool,
        {
            (_service_day(leg["tripId"]), trips[_trip_id(leg["tripId"])]["short_name"])
            for itinerary in itineraries
            for leg in itinerary["legs"]
            if _is_train(trips.get(_trip_id(leg.get("tripId") or "")))
            and _service_day(leg["tripId"])
        },
    )
    now = datetime.now(ZURICH).replace(microsecond=0)
    return [_connection(i, stations, trips, forecast, now, with_geometry) for i in itineraries]


def _is_train(trip) -> bool:
    return trip is not None and trip["mode"] == "train" and bool(trip["short_name"])


def _service_day(motis_trip_id: str) -> date | None:
    """`20261120_05:25_ch_...` -> the trip's service day, 20 November 2026."""
    try:
        return datetime.strptime(motis_trip_id[:8], "%Y%m%d").date()
    except ValueError:
        return None


def _connection(
    itinerary: dict,
    stations: dict,
    trips: dict,
    forecast: dict,
    now: datetime,
    with_geometry: bool = False,
) -> dict:
    legs = [leg for leg in itinerary["legs"] if not _transfer_within_station(leg)]
    sections = [_section(leg, stations, trips, forecast, now) for leg in legs]
    if with_geometry:
        for leg, section in zip(legs, sections, strict=True):
            section["geometry"] = _geometry(leg)
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
        **dict(
            zip(
                ("capacity1st", "capacity2nd"),
                highest_capacity(
                    [p for s in sections if s["journey"] for p in s["journey"]["passList"]]
                ),
                strict=True,
            )
        ),
        "sections": sections or None,
    }


def _geometry(leg: dict) -> dict | None:
    """The line a leg follows, as the router draws it.

    An encoded polyline (Google's algorithm) with its precision, the number of
    decimals of each coordinate. A walk follows the street network and, inside
    a station, says the lowest and highest floor it reaches (`levels`, 0 at
    street level). A ride runs straight from stop to stop: the timetable has
    no shapes.
    """
    line = leg.get("legGeometry") or {}
    if not line.get("points"):
        return None
    geometry = {"polyline": line["points"], "precision": line.get("precision") or 6}
    floors = {
        level
        for step in leg.get("steps") or []
        for level in (step.get("fromLevel"), step.get("toLevel"))
        if level is not None
    }
    floors = {int(f) if float(f).is_integer() else f for f in floors}
    if floors - {0}:
        geometry["levels"] = [min(floors | {0}), max(floors | {0})]
    return geometry


def _transfer_within_station(leg: dict) -> bool:
    """A walk from one platform to another of the same station is no section in /v1.

    A walk between two places that are no stops - an address to an address -
    is the whole connection.
    """
    start = leg["from"].get("parentId") or leg["from"].get("stopId")
    end = leg["to"].get("parentId") or leg["to"].get("stopId")
    return leg["mode"] == "WALK" and start is not None and start == end


def _section(leg: dict, stations: dict, trips: dict, forecast: dict, now: datetime) -> dict:
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
    known = trips.get(_trip_id(leg["tripId"]))
    trip = known or _trip_of_leg(leg)
    pass_list = [
        departure,
        *(
            _stop(p, stations, now, live, departs=True, arrives=True)
            for p in leg.get("intermediateStops") or []
        ),
        arrival,
    ]
    if _is_train(known):
        levels = forecast.get((_service_day(leg["tripId"]), known["short_name"]))
        # Where the train leaves from: not where this section gets off.
        for checkpoint in pass_list[:-1]:
            set_capacity(checkpoint, occupancy.at(levels, checkpoint["station"]["id"]))
    line = journey(
        trip_short_name=trip["short_name"],
        route_short_name=trip["route_short_name"],
        category=trip["category"],
        operator=trip["operator"],
        headsign=leg.get("headsign") or trip["headsign"],
        pass_list=pass_list,
        trip=trip_ref(_trip_id(leg["tripId"]), _service_day(leg["tripId"])),
    )
    line["capacity1st"], line["capacity2nd"] = highest_capacity(pass_list)
    return {
        "journey": line,
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


def _page(connections: list[dict], limit: int, page: int) -> list[dict]:
    """The page /v1 cuts out of the connections found.

    The offset is clamped into the first sixteen results, which is why a high
    page with a high limit quietly returns the tail of the window instead of
    an empty list.
    """
    offset = min(max(page * limit, 0), WINDOW - limit)
    return connections[offset : offset + limit]


def _validate(limit: int, page: int, via: list[str]) -> list[str]:
    problems = []
    if limit > MAX_LIMIT:
        problems.append(f"Maximal value of argument `limit` is {MAX_LIMIT}.")
    if page > MAX_PAGE:
        problems.append(f"Maximal value of argument `page` is {MAX_PAGE}.")
    if page < MIN_PAGE:
        problems.append(f"Minimal value of argument `page` is {MIN_PAGE}.")
    if len(via) > MAX_VIA:
        problems.append(f"Invalid via count (max {MAX_VIA} allowed).")
    return problems


def _number(value: str | None, default: int) -> int:
    """A count, as PHP would read it: anything unreadable is the default."""
    if not truthy(value):
        return default
    try:
        return int(float(value))
    except ValueError:
        return default


def _decimal(value: str | None) -> float | None:
    """A number with decimals, or None when there is none to read."""
    if not truthy(value):
        return None
    try:
        number = float(value.replace(",", "."))
    except ValueError:
        return None
    return number if number == number else None


def _is_arrival_time(value: str | None) -> bool:
    """`0`, `1`, `false`, `true` - and anything else leaves it alone."""
    return value in ("1", "true")


def _when(combined: str | None, date: str | None, time: str | None) -> datetime:
    """The moment to search from: `datetime`, or `date` and `time`, or now.

    Either half may be missing, and each falls back to the current day or the
    current minute on its own - which is what makes `time=23:50` without a date
    mean tonight.
    """
    now = datetime.now(ZURICH)

    # What cannot be read becomes the epoch, not now: strtotime() says false
    # and /v1 formats that as 1970-01-01 01:00.
    if truthy(combined):
        return _parse(combined) or phptime.EPOCH

    day = (_parse(date) or phptime.EPOCH) if truthy(date) else None
    clock = (_parse(time, reference=day or now) or phptime.EPOCH) if truthy(time) else None

    return (day or now).replace(
        hour=(clock or now).hour,
        minute=(clock or now).minute,
        second=0,
        microsecond=0,
    )


def _parse(value: str | None, reference: datetime | None = None) -> datetime | None:
    """What `strtotime()` would make of it, for the shapes clients send."""
    if not value:
        return None
    return phptime.parse(value, reference or datetime.now(ZURICH), convert_offset=True)
