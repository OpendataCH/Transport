"""`/ojp20`: the Open Journey Planner 2.0 interface, answered by our router.

OJP (CEN/TS 17118, VDV 431) is the XML interface the national journey planner
on opentransportdata.swiss speaks at `/ojp20`, and with it the apps of the
transport companies. MOTIS answers OJP 2.0 itself; this route passes requests
to it and puts right what an OJP client in Switzerland would trip over:

- **Stop ids.** MOTIS knows a stop by its own id: the dataset tag, and for a
  station the GTFS parent - `ch_Parentch:1:sloid:7000` for Bern,
  `ch_ch:1:sloid:7000:4:8` for its platform 8. Clients send the SLOID
  (`ch:1:sloid:7000`) or the DiDok number (`8507000`) and get back the
  SLOID, as the national planner answers (compared 19.11.2026). The router's
  own ids are accepted as they are; an operating day is written
  `2026-11-19`, as there, not `20261119`.
- **The service.** The router names a trip's line and little else. From the
  timetable the answer gets what the national planner gives as well: the
  public code (`IC1`, `20`), the product category (`IC`, InterCity) and the
  train number (`707`).
- **Namespace prefixes.** MOTIS finds elements by their literal prefix, so a
  request is written out again with OJP as the default namespace and `siri:`
  for SIRI, whatever prefixes the client chose.
- **Schema.** The answers of MOTIS 2.11.4 do not validate against the OJP 2.0
  schema: some elements are in the wrong namespace or order, some texts lack
  their `<Text>`, `Distance` counts the points of the drawn line instead of
  metres. Each of these is repaired here; see `repair`.

A departure board asks the router for twice the departures it wants and
keeps that many: MOTIS 2.11.4 counts a trip with real time twice while it
collects them and merges the two only afterwards, so Thun asked for ten
gives eight.

Only the four requests MOTIS knows pass, one at a time: trip, stop event,
trip info and location information, with the number of results asked for
kept in range. A journey plan takes one of the worker's router slots,
as `/v1/connections` does. A location request by name or stop id needs the
router's place search (`MOTIS_GEOCODING`): without it, MOTIS 2.11.4 crashes
on the lookup by id instead of refusing it.
"""

import re
import xml.etree.ElementTree as ET
from collections.abc import Iterator
from datetime import date
from xml.sax.saxutils import escape, quoteattr

import asyncpg
import httpx
from fastapi import APIRouter, Request
from fastapi.responses import Response

from .. import errors, settings
from . import db, occupancy
from .connections import TRIPS, _trip_id
from .router import plan_slot

router = APIRouter(include_in_schema=False)

OJP = "http://www.vdv.de/ojp"
SIRI = "http://www.siri.org.uk/siri"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

# The dataset tag the router puts in front of every id of our feed.
DATASET = "ch_"
# The GTFS parent of a station: the station's own id behind this word.
PARENT = "Parent"

# A request is a few hundred bytes; anything this large is not one.
MAX_REQUEST_BYTES = 64 * 1024

XML_TYPE = "text/xml; charset=utf-8"

REQUESTS = (
    "OJPTripRequest",
    "OJPStopEventRequest",
    "OJPTripInfoRequest",
    "OJPLocationInformationRequest",
)

SLOID = re.compile(r"ch:1:sloid:(\d+)")
DIDOK = re.compile(r"85(\d{5})")

# Elements whose text is a stop id.
STOP_REFS = {
    "StopPlaceRef",
    "StopPointRef",
    "ParentRef",
    "OriginStopPointRef",
    "DestinationStopPointRef",
}


def _o(name: str) -> str:
    return f"{{{OJP}}}{name}"


def _s(name: str) -> str:
    return f"{{{SIRI}}}{name}"


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


# --- stop ids ---------------------------------------------------------------


def to_router(stop_id: str) -> str:
    """The router's id for a stop id a client sends.

    A station (`ch:1:sloid:7000`, `8507000`, `8301700` for Milano Centrale)
    is the GTFS parent of its platforms; a platform (`ch:1:sloid:7000:4:8`)
    is itself. One station of 35 548 in the feed has no parent row (Bern
    Münsterplattform, ch:1:sloid:258); it is reachable by the router's id.
    """
    stop_id = stop_id.strip()
    if not stop_id or stop_id.startswith(DATASET):
        return stop_id
    if stop_id.startswith(PARENT):
        return DATASET + stop_id
    match = DIDOK.fullmatch(stop_id)
    if match:
        return f"{DATASET}{PARENT}ch:1:sloid:{int(match.group(1))}"
    if SLOID.fullmatch(stop_id) or stop_id.isdigit():
        return DATASET + PARENT + stop_id
    return DATASET + stop_id


def from_router(stop_id: str) -> str:
    """The id a client knows for one of the router's: the feed's own.

    As the national planner answers: a station by its SLOID
    (`ch:1:sloid:7000`), a platform too (`ch:1:sloid:7000:4:8`), a station
    abroad by its number (`8301700`).
    """
    stop_id = stop_id.strip().removeprefix(DATASET)
    return stop_id.removeprefix(PARENT)


def _day_to_router(day: str) -> str:
    return day.strip().replace("-", "")


def _day_from_router(day: str) -> str:
    """`20261119` as the national planner writes an operating day: `2026-11-19`."""
    day = day.strip()
    return f"{day[:4]}-{day[4:6]}-{day[6:]}" if len(day) == 8 and day.isdigit() else day


def _translate_days(root: ET.Element, translate) -> None:
    for element in root.iter(_o("OperatingDayRef")):
        if element.text:
            element.text = translate(element.text)


def _translate_ids(root: ET.Element, translate) -> None:
    for element in root.iter():
        if _local(element.tag) in STOP_REFS and element.text and len(element) == 0:
            element.text = translate(element.text)


# --- the request ------------------------------------------------------------

# The most departures the router hands out at once (its stoptimes limit).
ROUTER_MAX_STOP_EVENTS = 1024
# NumberOfResults: what is taken when it is below one or no number, and the most.
RESULTS = {"OJPTripRequest": (5, 32)}
OTHER_RESULTS = (10, ROUTER_MAX_STOP_EVENTS // 2)


def bound_results(root: ET.Element, kind: str) -> None:
    """Every NumberOfResults as a plain number in range."""
    default, highest = RESULTS.get(kind, OTHER_RESULTS)
    for element in root.iter():
        if _local(element.tag) != "NumberOfResults":
            continue
        text = (element.text or "").strip()
        wanted = int(text) if text.isascii() and text.isdigit() and len(text) < 10 else 0
        for child in list(element):
            element.remove(child)
        element.text = str(min(wanted, highest) if wanted >= 1 else default)


def widen_stop_events(root: ET.Element) -> int | None:
    """Ask the router for twice the departures wanted; the number wanted.

    The router counts a trip it has real time for once from the timetable
    and once from real time, and drops the double only after it has counted
    `n` - asked for ten, it may give eight. None when no number is given.
    """
    found = root.find(f".//{_o('OJPStopEventRequest')}/{_o('Params')}/{_o('NumberOfResults')}")
    if found is None or not (found.text or "").strip().isdigit():
        return None
    wanted = int(found.text)
    found.text = str(min(2 * wanted, ROUTER_MAX_STOP_EVENTS))
    return wanted


def keep_stop_events(root: ET.Element, wanted: int) -> None:
    """The first `wanted` departures of the router's answer."""
    for delivery in root.iter(_o("OJPStopEventDelivery")):
        for extra in delivery.findall(_o("StopEventResult"))[wanted:]:
            delivery.remove(extra)


class BadRequest(Exception):
    pass


# A request is a dozen levels deep; the writer recurses, so a deeper one is refused.
MAX_DEPTH = 64


def _depth(root: ET.Element) -> int:
    deepest, level = 0, [(root, 1)]
    while level:
        element, depth = level.pop()
        deepest = max(deepest, depth)
        level.extend((child, depth + 1) for child in element)
    return deepest


def parse_request(body: bytes) -> tuple[ET.Element, str]:
    """The request as a tree and the kind of request it is; BadRequest if it is none."""
    if len(body) > MAX_REQUEST_BYTES:
        raise BadRequest("The request is too large.")
    # No document type, and so no entities: nothing to expand, nothing to fetch.
    if b"<!DOCTYPE" in body.upper() or b"<!ENTITY" in body.upper():
        raise BadRequest("A document type declaration is not accepted.")
    try:
        root = ET.fromstring(body)
    except ET.ParseError as exc:
        raise BadRequest(f"The request is not well-formed XML: {exc}") from None
    if _depth(root) > MAX_DEPTH:
        raise BadRequest("The request is nested too deeply.")
    if root.tag != _o("OJP"):
        raise BadRequest(f"The root element must be OJP in the namespace {OJP}.")
    service_request = root.find(f"{_o('OJPRequest')}/{_s('ServiceRequest')}")
    if service_request is None:
        raise BadRequest("The request has no OJPRequest/siri:ServiceRequest.")
    requests = [child for child in service_request if _local(child.tag) in REQUESTS]
    if len(requests) > 1:
        raise BadRequest("One request at a time.")
    for kind in REQUESTS:
        found = service_request.find(_o(kind))
        if found is None:
            continue
        if kind == "OJPLocationInformationRequest" and not settings.MOTIS_GEOCODING:
            # The router answers a place search only with its search built,
            # and a lookup by stop id without it brings the router down.
            if found.find(f"{_o('InitialInput')}/{_o('GeoRestriction')}") is None:
                raise BadRequest("Only a search by area is available here, not by name or id.")
        return root, kind
    raise BadRequest("Supported are " + ", ".join(REQUESTS) + ".")


def write(root: ET.Element) -> bytes:
    """The tree with OJP as the default namespace and `siri:` for SIRI.

    Written by hand: ElementTree's `default_namespace` refuses the plain
    attributes OJP has (`version`), and the router needs exactly these
    prefixes. Elements of any other namespace are not part of OJP.
    """
    parts = ['<?xml version="1.0" encoding="utf-8"?>\n']
    _write(root, parts, top=True)
    return "".join(parts).encode()


def _name(tag: str) -> str:
    if tag.startswith(f"{{{OJP}}}"):
        return _local(tag)
    if tag.startswith(f"{{{SIRI}}}"):
        return "siri:" + _local(tag)
    raise BadRequest(f"An element outside the OJP and SIRI namespaces: {tag}")


def _write(element: ET.Element, parts: list[str], top: bool = False) -> None:
    name = _name(element.tag)
    parts.append("<" + name)
    if top:
        parts.append(f' xmlns="{OJP}" xmlns:siri="{SIRI}"')
    for key, value in element.attrib.items():
        if key == XML_LANG:
            key = "xml:lang"
        elif key.startswith("{"):
            continue  # schema locations and the like
        parts.append(f" {key}={quoteattr(value)}")
    if len(element) == 0 and not element.text:
        parts.append("/>")
    else:
        parts.append(">" + escape(element.text or ""))
        for child in element:
            _write(child, parts)
        parts.append(f"</{name}>")
    if element.tail and not top:
        parts.append(escape(element.tail))


# --- the answer -------------------------------------------------------------

# Elements in the wrong namespace in the router's answers, and where they belong.
RENAMED = {
    _s("StopPlaceRef"): _o("StopPlaceRef"),
    _o("LineRef"): _s("LineRef"),
    _o("DirectionRef"): _s("DirectionRef"),
    _o("OperatorRef"): _s("OperatorRef"),
}

# Elements of InternationalTextStructure: their text belongs in a <Text>.
TEXTS = {
    "StopPointName",
    "StopPlaceName",
    "NameSuffix",
    "PlannedQuay",
    "EstimatedQuay",
    "OriginText",
    "DestinationText",
    "PublishedServiceName",
    "RouteDescription",
    "Name",
}

# What the router writes as the name suffix of every call of a trip info, as a
# placeholder (`// TODO real data` in MOTIS): an accessibility value, no name.
FILLER = "PLATFORM_ACCESS_WITHOUT_ASSISTANCE"

# Elements that are invalid or meaningless without children.
DROPPED_WHEN_EMPTY = {
    "Places",
    "LinkProjection",
    "ProductCategory",
    "ServiceArrival",
    "ServiceDeparture",
}

# The order of the children, from the OJP 2.0 schema (OJP_JourneySupport.xsd,
# OJP_PlaceSupport.xsd, OJP_Trips.xsd), for the elements the router gets wrong.
_CALL = [
    "siri:StopPointRef",
    "StopPointName",
    "NameSuffix",
    "PlannedQuay",
    "EstimatedQuay",
    "GeoPosition",
    "ServiceArrival",
    "ServiceDeparture",
    "DistributorInterchangeId",
    "FeederInterchangeId",
    "MeetsViaRequest",
    "Order",
    "RequestStop",
    "UnplannedStop",
    "NotServicedStop",
    "NoBoardingAtStop",
    "NoAlightingAtStop",
    "siri:ExpectedDepartureOccupancy",
    "siri:ExpectedDepartureCapacities",
    "Attribute",
    "SituationFullRefs",
]
_SERVICE = [
    "ConventionalModeOfOperation",
    "OperatingDayRef",
    "JourneyRef",
    "PublicCode",
    "siri:LineRef",
    "siri:DirectionRef",
    "Mode",
    "ProductCategory",
    "PublishedServiceName",
    "TrainNumber",
    "siri:VehicleRef",
    "OperatorRefs",
    "RouteDescription",
    "Via",
    "Restricted",
    "RestrictionNote",
    "Attribute",
    "OriginStopPointRef",
    "OriginText",
    "siri:OperatorRef",
    "siri:ProductCategoryRef",
    "siri:ServiceFeatureRef",
    "siri:VehicleFeatureRef",
    "DestinationStopPointRef",
    "DestinationText",
    "Unplanned",
    "Cancelled",
    "Deviation",
    "UndefinedDelay",
    "Occupancy",
    "JourneyRelations",
    "BookingArrangements",
    "ReservationNeeded",
    "SituationFullRefs",
    "Extension",
]
_PLACE_REF = [
    "siri:StopPointRef",
    "StopPlaceRef",
    "GeoPosition",
    "TopographicPlaceRef",
    "PointOfInterestRef",
    "AddressRef",
    "Name",
    "AllowedSystemId",
]
ORDER = {
    "CallAtStop": _CALL,
    "PreviousCall": _CALL,
    "OnwardCall": _CALL,
    "LegBoard": _CALL,
    "LegIntermediate": _CALL,
    "LegAlight": _CALL,
    "Service": _SERVICE,
    "PlaceRef": _PLACE_REF,
    "TrackSectionStart": _PLACE_REF,
    "TrackSectionEnd": _PLACE_REF,
    "StopPoint": [
        "siri:StopPointRef",
        "StopPointName",
        "NameSuffix",
        "PlannedQuay",
        "EstimatedQuay",
        "PrivateCode",
        "ParentRef",
        "TopographicPlaceRef",
        "WheelchairAccessible",
        "Lighting",
        "Covered",
    ],
    "StopPlace": [
        "StopPlaceRef",
        "StopPlaceName",
        "NameSuffix",
        "PrivateCode",
        "TopographicPlaceRef",
        "WheelchairAccessible",
        "Lighting",
        "Covered",
    ],
}
_RANKS = {
    parent: {(_s(n[5:]) if n.startswith("siri:") else _o(n)): i for i, n in enumerate(names)}
    for parent, names in ORDER.items()
}


def _language(root: ET.Element) -> str:
    found = root.find(f".//{_s('DefaultLanguage')}")
    return (found.text or "").strip() if found is not None and found.text else "de"


def journeys(root: ET.Element) -> list[str]:
    """The trips of the router's answer, as the timetable names them."""
    found = {_trip_id(e.text.strip()) for e in root.iter(_o("JourneyRef")) if e.text}
    return sorted(found)


def repair(root: ET.Element, trips: dict | None = None) -> None:
    """Make the router's answer valid OJP 2.0, with the stop ids clients know.

    `trips` are the timetable's rows for `journeys(root)`, by trip id.
    """
    language = _language(root)
    for element in list(root.iter()):
        if element.tag in RENAMED:
            element.tag = RENAMED[element.tag]
        if (
            element.tag.startswith(f"{{{OJP}}}")
            and _local(element.tag) in TEXTS
            and len(element) == 0
            and (element.text or "").strip()
        ):
            text = ET.SubElement(element, _o("Text"), {XML_LANG: language})
            text.text, element.text = element.text, None
    _translate_ids(root, from_router)
    _translate_days(root, _day_from_router)
    _prune(root)
    _complete_services(root, trips or {}, language)
    _mend_tracks(root)
    for element in root.iter():
        ranks = _RANKS.get(_local(element.tag))
        if ranks:
            children = list(element)
            children.sort(key=lambda child: ranks.get(child.tag, len(ranks)))
            element[:] = children


# --- occupancy ----------------------------------------------------------------

# The calls a vehicle leaves from: where occupancy is given, as the national
# planner gives it.
DEPARTING_CALLS = ("LegBoard", "LegIntermediate", "CallAtStop")


def _didok(stop_id: str) -> int | None:
    """`ch:1:sloid:7000:4:8` -> 8507000, the number the forecast names a station by."""
    match = SLOID.match(stop_id)
    if match and len(match.group(1)) <= 5:
        return 8500000 + int(match.group(1))
    return int(stop_id) if stop_id.isdigit() else None


def _runs(root: ET.Element) -> Iterator[tuple[ET.Element, tuple[date, str, str]]]:
    """Each leg and stop event with a train, and the train: (day, operator, number)."""
    for run in [*root.iter(_o("TimedLeg")), *root.iter(_o("StopEvent"))]:
        service = run.find(_o("Service"))
        if service is None:
            continue
        day = (service.findtext(_o("OperatingDayRef")) or "").strip()
        operator = (service.findtext(_s("OperatorRef")) or "").strip()
        number = (service.findtext(_o("TrainNumber")) or "").strip()
        try:
            yield run, (date.fromisoformat(day), operator, number)
        except ValueError:
            continue


def trains(root: ET.Element) -> set[tuple[date, str, str]]:
    """The trains of a repaired answer, to look their occupancy up."""
    return {train for _, train in _runs(root) if all(train)}


def add_occupancy(root: ET.Element, forecast: dict) -> None:
    """The expected occupancy of each departure, from the railways' forecast.

    `forecast` is `occupancy.lookup` for `trains(root)`. A call it has no
    word on is left as it is.
    """
    if not forecast:
        return
    for run, train in _runs(root):
        for name in DEPARTING_CALLS:
            for call in run.iter(_o(name)):
                if call.find(_o("ServiceDeparture")) is None:
                    continue
                station = _didok((call.findtext(_s("StopPointRef")) or "").strip())
                levels = forecast.get((*train, station))
                if not levels:
                    continue
                for fare_class, level in zip(("firstClass", "secondClass"), levels, strict=True):
                    if level is None:
                        continue
                    expected = ET.SubElement(call, _s("ExpectedDepartureOccupancy"))
                    ET.SubElement(expected, _s("FareClass")).text = fare_class
                    ET.SubElement(expected, _s("OccupancyLevel")).text = occupancy.NAMES[level]
                ranks = _RANKS[_local(call.tag)]
                call[:] = sorted(call, key=lambda child: ranks.get(child.tag, len(ranks)))


def _mend_tracks(root: ET.Element) -> None:
    """The line of a leg: the end's stop where it belongs, no length in points.

    The router writes the end stop of a timed leg's track section into its
    start; writes the walk to the first train and from the last one as a
    continuous leg, where the national planner has a transfer; puts a
    transfer's track section straight into PathGuidance, where
    OJP wants it in a PathGuidanceSection; and gives the tracks of timed,
    continuous and transfer legs the number of points of the drawn line as
    `Length`, which OJP counts in metres. Only a trip info's JourneyTrack has
    the true length.
    """
    for track in root.iter(_o("LegTrack")):
        for section in track.iter(_o("TrackSection")):
            start = section.find(_o("TrackSectionStart"))
            end = section.find(_o("TrackSectionEnd"))
            refs = start.findall(_s("StopPointRef")) if start is not None else []
            if len(refs) == 2 and end is not None and end.find(_s("StopPointRef")) is None:
                start.remove(refs[1])
                end.insert(0, refs[1])
    for leg in root.iter(_o("Leg")):
        walk = leg.find(_o("ContinuousLeg"))
        if walk is not None and _between_stops(walk):
            index = list(leg).index(walk)
            leg.remove(walk)
            leg.insert(index, _transfer(walk))
    for guidance in root.iter(_o("PathGuidance")):
        for index, child in enumerate(list(guidance)):
            if child.tag == _o("TrackSection"):
                wrapper = ET.Element(_o("PathGuidanceSection"))
                wrapper.append(child)
                guidance.remove(child)
                guidance.insert(index, wrapper)
    measured = {id(s) for t in root.iter(_o("JourneyTrack")) for s in t.iter(_o("TrackSection"))}
    for parent in root.iter():
        if parent.tag == _o("ContinuousLeg") or (
            parent.tag == _o("TrackSection") and id(parent) not in measured
        ):
            for length in parent.findall(_o("Length")):
                parent.remove(length)


# The categories of the feed (route_desc) by their names, as the national
# planner writes them. One not listed keeps its short name alone.
CATEGORIES = {
    "B": "Bus",
    "BN": "Nachtbus",
    "BAT": "Schiff",
    "EC": "EuroCity",
    "EN": "EuroNight",
    "EV": "Ersatzverkehr",
    "EXT": "Extrazug",
    "FUN": "Standseilbahn",
    "GB": "Gondelbahn",
    "IC": "InterCity",
    "ICE": "InterCityExpress",
    "ICN": "InterCity-Neigezug",
    "IR": "InterRegio",
    "IRE": "InterRegio-Express",
    "M": "Metro",
    "NJ": "Nightjet",
    "PB": "Luftseilbahn",
    "PE": "Panorama-Express",
    "R": "Regio",
    "RE": "RegioExpress",
    "RJX": "railjet xpress",
    "S": "S-Bahn",
    "SL": "Sesselbahn",
    "SN": "Nacht-S-Bahn",
    "T": "Tram",
    "TGV": "TGV",
}


def _text(parent: ET.Element, name: str, value: str, language: str) -> None:
    element = ET.SubElement(parent, _o(name))
    ET.SubElement(element, _o("Text"), {XML_LANG: language}).text = value


def _complete_services(root: ET.Element, trips: dict, language: str) -> None:
    """Public code, category and train number, where the router has none.

    The public code is the line as published (`IC1`, `20`); the rest comes
    from the timetable: the category as the mode's short name, as the
    national planner writes it and the fare service needs it, and as the
    product category. A trip it does not have - an extra train from real
    time - keeps what the router gave.
    """
    for service in root.iter(_o("Service")):
        if service.find(_o("PublicCode")) is None:
            published = service.find(_o("PublishedServiceName"))
            code = "".join(published.itertext()).strip() if published is not None else ""
            if code:
                ET.SubElement(service, _o("PublicCode")).text = code
        trip = trips.get(_trip_id((service.findtext(_o("JourneyRef")) or "").strip()))
        if trip is None:
            continue
        category = trip["category"]
        mode = service.find(_o("Mode"))
        if category and mode is not None and mode.find(_o("ShortName")) is None:
            # The fare service (OJPFare, NOVA) prices a leg only with it.
            _text(mode, "ShortName", category, language)
        if category and service.find(_o("ProductCategory")) is None:
            product = ET.SubElement(service, _o("ProductCategory"))
            if category in CATEGORIES:
                _text(product, "Name", CATEGORIES[category], language)
            _text(product, "ShortName", category, language)
        if trip["short_name"] and service.find(_o("TrainNumber")) is None:
            ET.SubElement(service, _o("TrainNumber")).text = trip["short_name"]


def _stop_of(place: ET.Element | None) -> bool:
    return place is not None and (
        place.find(_s("StopPointRef")) is not None or place.find(_o("StopPlaceRef")) is not None
    )


def _between_stops(leg: ET.Element) -> bool:
    """Whether a continuous leg is a walk from one stop to another."""
    mode = leg.findtext(f"{_o('Service')}/{_o('PersonalMode')}")
    return (
        (mode or "").strip() == "foot"
        and _stop_of(leg.find(_o("LegStart")))
        and _stop_of(leg.find(_o("LegEnd")))
    )


def _transfer(walk: ET.Element) -> ET.Element:
    """The walk as the transfer the national planner writes for it.

    A continuous leg is the way from an address or a place; between two
    stops the national planner writes a transfer on foot, with the line
    walked as its path guidance.
    """
    transfer = ET.Element(_o("TransferLeg"))
    ET.SubElement(transfer, _o("TransferType")).text = "walk"
    for name in ("LegStart", "LegEnd", "Duration"):
        found = walk.find(_o(name))
        if found is not None:
            transfer.append(found)
    sections = walk.findall(f"{_o('LegTrack')}/{_o('TrackSection')}")
    if sections:
        guidance = ET.SubElement(transfer, _o("PathGuidance"))
        guidance.extend(sections)
    return transfer


def _prune(parent: ET.Element) -> None:
    seen_public_code = False
    for child in list(parent):
        _prune(child)
        name = _local(child.tag)
        if child.tag == _o("Distance") and _local(parent.tag) == "Trip":
            # The router sums the number of points of each leg's line.
            parent.remove(child)
        elif name in DROPPED_WHEN_EMPTY and len(child) == 0 and not (child.text or "").strip():
            parent.remove(child)
        elif child.tag == _o("NameSuffix") and "".join(child.itertext()).strip() == FILLER:
            parent.remove(child)
        elif child.tag == _o("PublicCode"):
            if seen_public_code:
                parent.remove(child)
            seen_public_code = True


# --- the route --------------------------------------------------------------


def _plain(status: int, message: str) -> Response:
    return Response(message + "\n", status_code=status, media_type="text/plain")


@router.post("/ojp20")
async def ojp20(request: Request) -> Response:
    client: httpx.AsyncClient | None = getattr(request.app.state, "motis", None)
    if client is None or not settings.MOTIS_URL:
        return _plain(503, "The router is not configured.")
    try:
        root, kind = parse_request(await request.body())
        bound_results(root, kind)
        wanted = widen_stop_events(root) if kind == "OJPStopEventRequest" else None
        _translate_ids(root, to_router)
        _translate_days(root, _day_to_router)
        body = write(root)
    except BadRequest as exc:
        return _plain(400, str(exc))

    try:
        if kind == "OJPTripRequest":
            async with plan_slot():
                answer = await _post(client, body)
        else:
            answer = await _post(client, body)
    except errors.ApiError as exc:
        return _plain(exc.status_code, exc.message)
    except httpx.HTTPError:
        return _plain(503, "The router is not reachable.")

    if answer.status_code >= 400:
        # The router says what it could not do in a line of JSON: a stop it
        # does not know is the client's mistake, anything else is ours.
        status = 400 if answer.status_code < 500 else 502
        return _plain(status, f"The router answered {answer.status_code}: {answer.text[:300]}")
    try:
        tree = ET.fromstring(answer.content)
    except ET.ParseError:
        return _plain(502, "The router's answer is not XML.")
    if wanted is not None:
        keep_stop_events(tree, wanted)
    repair(tree, await _trips(request, journeys(tree)))
    add_occupancy(tree, await _occupancy(request, trains(tree)))
    ET.indent(tree)
    try:
        return Response(write(tree), media_type=XML_TYPE)
    except BadRequest as exc:  # the router wrote an element of a third namespace
        return _plain(502, str(exc))


async def _trips(request: Request, trip_ids: list[str]) -> dict:
    """The timetable's rows for these trips; none without the timetable.

    The router's answer is complete without them, so a database that is not
    there or not loaded yet costs the extras, not the answer.
    """
    pool = getattr(request.app.state, "timetable", None)
    if pool is None or not trip_ids:
        return {}
    try:
        return {r["trip_id"]: r for r in await db.fetch(pool, TRIPS, trip_ids)}
    except errors.ApiError:
        return {}


async def _occupancy(request: Request, wanted: set) -> dict:
    """The forecast for these trains; none without it, as for `_trips`."""
    pool = getattr(request.app.state, "timetable", None)
    if pool is None or not wanted:
        return {}
    try:
        return await occupancy.lookup(pool, wanted)
    except (asyncpg.PostgresError, OSError):
        return {}


async def _post(client: httpx.AsyncClient, body: bytes) -> httpx.Response:
    return await client.post("/ojp20", content=body, headers={"content-type": XML_TYPE})
