"""`POST /v1/fare`: what a connection costs, from the national fare service.

The fares of Swiss public transport are NOVA's, and reachable only through
its OJP interface on opentransportdata.swiss (`/ojpfare`, beta). This route
takes a connection as `/v1/connections` returned it and answers the price of
a point-to-point ticket (Streckenbillett), full and with a half-fare card, in
both classes - what the timetables of the railways show as "ab CHF".

The plan allows 20 000 requests a day and 50 a minute, and every connection
search on this API would need two (full fare and half fare). So:

- **Prices are kept** for FARE_CACHE_DAYS days per route: the sections'
  stations, category and operator - not the time, a point-to-point fare does
  not depend on it - and the timetable year, as fares change with the
  timetable in mid-December.
- **The fare service is asked at most** FARE_PER_MINUTE times a minute and
  FARE_PER_DAY times a day across all workers, counted in Redis. Beyond that
  the route answers 503 rather than spend the key's quota.
- A route NOVA cannot price is remembered for an hour, so that one client
  cannot spend the quota on it.

What it needs of a section, NOVA told us by refusing the rest (20.11.2026):
the stations (DiDok numbers do), the times, the line, the operator by its
number, and the category as the mode's short name.
"""

import hashlib
import json
import logging
import time
import xml.etree.ElementTree as ET
from datetime import UTC, date, datetime
from typing import Annotated, Any

import httpx
from fastapi import APIRouter, Body, Request
from fastapi.responses import JSONResponse

from .. import settings
from .names import operators

log = logging.getLogger("transport_api.timetable.fare")

router = APIRouter()

OJP = "http://www.vdv.de/ojp"
SIRI = "http://www.siri.org.uk/siri"
XML_LANG = "{http://www.w3.org/XML/1998/namespace}lang"

# The means of transport OJP knows, by the feed's category (route_desc).
MODES = {
    "B": "bus",
    "BN": "bus",
    "BP": "bus",
    "EXB": "bus",
    "T": "tram",
    "M": "metro",
    "BAT": "water",
    "FAE": "water",
    "FUN": "funicular",
    "PB": "telecabin",
    "GB": "telecabin",
    "SL": "telecabin",
}

HALF_FARE = (
    "<EntitlementProducts><EntitlementProduct>"
    "<FareAuthorityRef>ch:1:NOVA</FareAuthorityRef>"
    "<EntitlementProductRef>HTA</EntitlementProductRef>"
    "<EntitlementProductName>Halbtax-Abo</EntitlementProductName>"
    "</EntitlementProduct></EntitlementProducts>"
)
# Without a card NOVA still wants the element, empty; left out, it fails.
NO_CARD = "<EntitlementProducts/>"


class Unpriceable(Exception):
    """The connection has nothing NOVA could price."""


def _operator_id(name: str | None) -> str | None:
    """`SBB` -> `11`: the number /v1 hides behind the operator's name."""
    if not name:
        return None
    by_id, _ = operators()
    return next((agency for agency, known in by_id.items() if known == name), None)


def _utc(value: str) -> str:
    """`2026-11-20T07:31:00+0100` -> `2026-11-20T06:31:00Z`."""
    moment = datetime.strptime(value, "%Y-%m-%dT%H:%M:%S%z")
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def rides(connection: dict) -> list[dict]:
    """The sections of a /v1 connection that are rides, as NOVA needs them."""
    found = []
    for section in connection.get("sections") or []:
        journey = section.get("journey")
        if not isinstance(journey, dict):
            continue  # a walk costs nothing
        departure, arrival = section.get("departure") or {}, section.get("arrival") or {}
        start = (departure.get("station") or {}).get("id")
        end = (arrival.get("station") or {}).get("id")
        operator = _operator_id(journey.get("operator"))
        if not (start and end and departure.get("departure") and arrival.get("arrival")):
            raise Unpriceable("A section has no stations or times.")
        if not operator or not journey.get("category"):
            raise Unpriceable(f"No fare is known for {journey.get('operator')!r}.")
        found.append(
            {
                "from": str(start),
                "to": str(end),
                "departure": _utc(departure["departure"]),
                "arrival": _utc(arrival["arrival"]),
                "category": journey["category"],
                "operator": operator,
            }
        )
    if not found:
        raise Unpriceable("The connection has no ride to price.")
    return found


def timetable_year(day: date) -> int:
    """The timetable year a day belongs to: from the second Sunday of December on, the next."""
    second_sunday = 8 + (6 - date(day.year, 12, 8).weekday()) % 7
    return day.year + 1 if (day.month, day.day) >= (12, second_sunday) else day.year


def cache_key(legs: list[dict]) -> str:
    year = timetable_year(date.fromisoformat(legs[0]["departure"][:10]))
    route = [(leg["from"], leg["to"], leg["category"], leg["operator"]) for leg in legs]
    digest = hashlib.sha1(json.dumps([year, route]).encode()).hexdigest()
    return f"fare:route:{digest}"


def request_body(legs: list[dict], card: str) -> bytes:
    """An OJP fare request for these rides, for one adult."""

    def text(value: str) -> str:
        return f'<Text xml:lang="de">{_escape(value)}</Text>'

    xml_legs = "".join(
        f"<Leg><Id>{n}</Id><TimedLeg>"
        f"<LegBoard><siri:StopPointRef>{_escape(leg['from'])}</siri:StopPointRef>"
        f"<StopPointName>{text(leg['from'])}</StopPointName>"
        f"<ServiceDeparture><TimetabledTime>{leg['departure']}</TimetabledTime></ServiceDeparture>"
        f"<Order>1</Order></LegBoard>"
        f"<LegAlight><siri:StopPointRef>{_escape(leg['to'])}</siri:StopPointRef>"
        f"<StopPointName>{text(leg['to'])}</StopPointName>"
        f"<ServiceArrival><TimetabledTime>{leg['arrival']}</TimetabledTime></ServiceArrival>"
        f"<Order>2</Order></LegAlight>"
        f"<Service><OperatingDayRef>{leg['departure'][:10]}</OperatingDayRef>"
        f"<JourneyRef>{n}</JourneyRef>"
        f"<siri:LineRef>{_escape(leg['category'])}</siri:LineRef>"
        f"<Mode><PtMode>{MODES.get(leg['category'], 'rail')}</PtMode>"
        f"<ShortName>{text(leg['category'])}</ShortName></Mode>"
        f"<siri:OperatorRef>{_escape(leg['operator'])}</siri:OperatorRef></Service>"
        f"</TimedLeg></Leg>"
        for n, leg in enumerate(legs, 1)
    )
    now = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<OJP xmlns="{OJP}" xmlns:siri="{SIRI}" version="2.0"><OJPRequest><siri:ServiceRequest>'
        "<siri:ServiceRequestContext><siri:Language>de</siri:Language></siri:ServiceRequestContext>"
        f"<siri:RequestTimestamp>{now}</siri:RequestTimestamp>"
        "<siri:RequestorRef>transport.opendata.ch</siri:RequestorRef>"
        f"<OJPFareRequest><siri:RequestTimestamp>{now}</siri:RequestTimestamp>"
        f"<TripFareRequest><Trip><Id>1</Id><Duration>PT0M</Duration>"
        f"<StartTime>{legs[0]['departure']}</StartTime><EndTime>{legs[-1]['arrival']}</EndTime>"
        f"<Transfers>{len(legs) - 1}</Transfers>{xml_legs}</Trip></TripFareRequest>"
        "<Params><FareAuthorityFilter>ch:1:NOVA</FareAuthorityFilter>"
        "<PassengerCategory>Adult</PassengerCategory><TravelClass>second</TravelClass>"
        f"<Traveller><Age>30</Age><PassengerCategory>Adult</PassengerCategory>{card}</Traveller>"
        "</Params></OJPFareRequest></siri:ServiceRequest></OJPRequest></OJP>"
    ).encode()


def _escape(value: str) -> str:
    return value.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def prices(answer: bytes, legs: int) -> dict[str, float]:
    """{"1st": 45.5, "2nd": 26.5}: per class, the products that cover the whole trip.

    NOVA answers a product per class and stretch of legs; one stretch from
    the first leg to the last is the ticket, several that follow on from
    each other are added up.
    """
    root = ET.fromstring(answer)
    by_class: dict[str, list[tuple[int, int, float]]] = {}
    for result in root.iter(f"{{{OJP}}}TripFareResult"):
        try:
            first = int(result.findtext(f"{{{OJP}}}FromLegIdRef") or "")
            last = int(result.findtext(f"{{{OJP}}}ToLegIdRef") or "")
        except ValueError:
            continue
        for product in result.iter(f"{{{OJP}}}FareProduct"):
            fare_class = (product.findtext(f"{{{OJP}}}FareClass") or "").strip()
            price = product.findtext(f"{{{OJP}}}Price")
            name = {"firstClass": "1st", "secondClass": "2nd"}.get(fare_class)
            if name and price:
                by_class.setdefault(name, []).append((first, last, float(price)))
    found = {}
    for name, stretches in by_class.items():
        whole = [p for f, t, p in stretches if f == 1 and t == legs]
        if whole:
            found[name] = min(whole)
            continue
        covered, total = 1, 0.0
        for f, t, p in sorted(stretches):
            if f == covered:
                covered, total = t + 1, total + p
        if covered == legs + 1:
            found[name] = round(total, 2)
    return found


class Busy(Exception):
    """The quota for the fare service is spent for now."""


async def _spend(redis, calls: int) -> None:
    """Count `calls` against the minute's and the day's allowance, or raise Busy."""
    minute = f"fare:minute:{int(time.time() // 60)}"
    day = f"fare:day:{date.today().isoformat()}"
    async with redis.pipeline(transaction=False) as pipe:
        pipe.incrby(minute, calls).expire(minute, 120)
        pipe.incrby(day, calls).expire(day, 2 * 86400)
        used_minute, _, used_day, _ = await pipe.execute()
    if used_minute > settings.FARE_PER_MINUTE or used_day > settings.FARE_PER_DAY:
        raise Busy


async def _ask(client: httpx.AsyncClient, legs: list[dict], card: str) -> dict[str, float]:
    response = await client.post(
        settings.OJP_FARE_URL,
        content=request_body(legs, card),
        headers={
            "Authorization": f"Bearer {settings.OJP_FARE_KEY}",
            "Content-Type": "application/xml",
            "User-Agent": f"transport.opendata.ch/{settings.VERSION}",
        },
        timeout=20,
    )
    if response.status_code >= 400:
        return {}
    return prices(response.content, len(legs))


async def fare_of(redis, client: httpx.AsyncClient, connection: dict) -> dict | None:
    """The fares of a connection, from the cache or NOVA; None if NOVA has none."""
    legs = rides(connection)
    key = cache_key(legs)
    kept = await redis.get(key)
    if kept is not None:
        return json.loads(kept)
    await _spend(redis, 2)
    full = await _ask(client, legs, NO_CARD)
    half = await _ask(client, legs, HALF_FARE)
    fares = {
        name: {"full": full.get(name), "halfFare": half.get(name)}
        for name in ("2nd", "1st")
        if full.get(name) is not None or half.get(name) is not None
    }
    answer = {"currency": "CHF", "product": "Streckenbillett", "fares": fares} if fares else None
    keep = settings.FARE_CACHE_DAYS * 86400 if answer else 3600
    await redis.set(key, json.dumps(answer), ex=keep)
    return answer


def _error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"errors": [{"message": message}]}, status_code=status)


@router.post(
    "/fare",
    summary="What a connection costs",
    description=(
        "Send one connection as `/connections` returned it. The answer is the "
        "price of a point-to-point ticket for one adult, full and with a "
        "half-fare card, in both classes, from the national fare service "
        "(NOVA). Prices are kept for days; when the shared quota is spent "
        "for the minute or the day, the answer is 503."
    ),
)
async def fare(request: Request, connection: Annotated[dict[str, Any], Body(...)]) -> JSONResponse:
    statistics = getattr(request.app.state, "statistics", None)
    redis = getattr(statistics, "redis", None)
    if not settings.OJP_FARE_KEY or redis is None:
        return _error(503, "Fares are not available here.")
    try:
        async with httpx.AsyncClient() as client:
            answer = await fare_of(redis, client, connection)
    except Unpriceable as exc:
        return _error(400, str(exc))
    except (ValueError, KeyError, TypeError, AttributeError):
        return _error(400, "This is not a connection as /connections returns it.")
    except Busy:
        return _error(503, "Too many fares asked for; try again in a minute.")
    except (httpx.HTTPError, ET.ParseError) as exc:
        log.warning("fare service failed: %r", exc)
        return _error(502, "The fare service did not answer.")
    if answer is None:
        return _error(404, "The fare service knows no price for this connection.")
    return JSONResponse(answer)
