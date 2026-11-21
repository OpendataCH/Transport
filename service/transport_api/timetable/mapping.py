"""Timetable rows in the shapes of /v1.

The shapes are /v1's, key for key, so that `tools/comparison.py` can hold the
two side by side; see models.py. Where /v1 has a habit a client may lean on,
the habit is kept and named. The values come from a different source and
differ where the sources do - the operator is the GTFS agency name, not
search.ch's abbreviation, and there are no addresses.
"""

from datetime import UTC, datetime, timedelta
from typing import Any

from ..mapping import ZURICH, iso


def coordinate(lat: float | None, lon: float | None) -> dict:
    """`x` is the latitude and `y` the longitude, as /v1 names them."""
    if lat is None or lon is None:
        return {"type": "WGS84", "x": None, "y": None}
    return {"type": "WGS84", "x": round(lat, 6), "y": round(lon, 6)}


def location(
    id_: str | None,
    name: str | None,
    lat: float | None,
    lon: float | None,
    *,
    distance: float | None = None,
    icon: Any = ...,
) -> dict:
    """The location shape. `icon` is left out unless given, as /v1 does."""
    entry: dict[str, Any] = {
        "id": id_,
        "name": name,
        "score": None,
        "coordinate": coordinate(lat, lon),
        "distance": distance,
    }
    if icon is not ...:
        entry["icon"] = icon
    return entry


def service_day_start(day) -> datetime:
    """Where GTFS counts a service day's seconds from: noon minus twelve hours.

    Midnight on most days; on the two days the clocks change it is an hour
    off midnight, which is exactly what keeps the published times right.

    The arithmetic is in UTC: Python adds and subtracts on a zoneinfo
    datetime in wall-clock time, so twelve hours back from noon in Zurich is
    midnight even on those two days - and the station board, which counts
    real seconds from `.timestamp()`, looked an hour off the requested time.
    """
    noon = datetime(day.year, day.month, day.day, 12, tzinfo=ZURICH)
    return noon.astimezone(UTC) - timedelta(hours=12)


def moment(day, seconds: int) -> datetime:
    return (service_day_start(day) + timedelta(seconds=seconds)).astimezone(ZURICH)


def prognosis(
    arrival: datetime | None,
    departure: datetime | None,
    arrival_delay: int | None,
    departure_delay: int | None,
    now: datetime,
) -> dict:
    """The real-time picture, built the way /v1 builds it from search.ch.

    Delays are whole minutes. Only a positive delay moves the time - /v1
    announces an early train as punctual. A delay for a time the stop does not
    have is added to *now*: /v1 dates a missing scheduled time to the moment
    of the request, and the head stop of a station board carries an arrival
    prognosis because of it.
    """
    return {
        "platform": None,
        "arrival": _delayed(arrival, arrival_delay, now),
        "departure": _delayed(departure, departure_delay, now),
        "capacity1st": None,
        "capacity2nd": None,
    }


def _delayed(scheduled: datetime | None, minutes: int | None, now: datetime) -> str | None:
    if minutes is None:
        return None
    base = scheduled if scheduled is not None else now
    return iso(base + timedelta(minutes=minutes) if minutes > 0 else base)


def stop(
    station: dict,
    arrival: datetime | None,
    departure: datetime | None,
    platform: str | None,
    arrival_delay: int | None,
    departure_delay: int | None,
    now: datetime,
) -> dict:
    """One checkpoint, with `delay` worked out from the prognosis as /v1 does."""
    forecast = prognosis(arrival, departure, arrival_delay, departure_delay, now)
    delay = None
    if forecast["arrival"] and arrival:
        delay = _minutes(forecast["arrival"], arrival)
    if forecast["departure"] and departure:
        delay = _minutes(forecast["departure"], departure)
    return {
        "station": station,
        "arrival": iso(arrival) if arrival else None,
        "arrivalTimestamp": int(arrival.timestamp()) if arrival else None,
        "departure": iso(departure) if departure else None,
        "departureTimestamp": int(departure.timestamp()) if departure else None,
        "delay": delay,
        "platform": platform,
        "prognosis": forecast,
        "realtimeAvailability": None,
        "location": dict(station),
    }


def _minutes(forecast: str, scheduled: datetime) -> int | float:
    seconds = int(datetime.strptime(forecast, "%Y-%m-%dT%H:%M:%S%z").timestamp()) - int(
        scheduled.timestamp()
    )
    return seconds // 60 if seconds % 60 == 0 else seconds / 60


def line_number(
    short_name: str | None, category: str | None, trip_short_name: str | None
) -> str | None:
    """`S10` with category `S` is line `10`, as search.ch numbers it.

    A train without a line - an ICE, a TER, whose short name is just its
    category - is numbered by search.ch with its train number instead.
    """
    if short_name and category and short_name.startswith(category):
        if short_name != category:
            return short_name[len(category) :]
        return journey_name(trip_short_name) or short_name
    return short_name


def destination(headsign: str | None) -> str | None:
    """`Neuchâtel | Avenches` - a train that splits - is `Neuchâtel` on search.ch."""
    return headsign.split(" | ", 1)[0] if headsign else headsign


def journey_name(trip_short_name: str | None) -> str | None:
    """search.ch writes a train number six digits wide: `015145`."""
    if trip_short_name and trip_short_name.isdigit():
        return trip_short_name.zfill(6)
    return trip_short_name


def journey(
    *,
    trip_short_name: str | None,
    route_short_name: str | None,
    category: str | None,
    operator: str | None,
    headsign: str | None,
    pass_list: list[dict],
    trip: dict | None = None,
) -> dict:
    return {
        "name": journey_name(trip_short_name),
        "category": category,
        "subcategory": None,
        "categoryCode": category_code(category),
        "number": line_number(route_short_name, category, trip_short_name),
        "operator": operator,
        "to": destination(headsign),
        "passList": pass_list,
        "capacity1st": None,
        "capacity2nd": None,
        "trip": trip,
    }


def trip_ref(trip_id: str | None, day) -> dict | None:
    """`{"id": trip_id, "date": "YYYY-MM-DD"}`, or None without either."""
    if not trip_id or day is None:
        return None
    return {"id": trip_id, "date": day.isoformat()}


def set_capacity(stop_: dict, levels: tuple | None) -> None:
    """The occupancy a train leaves this stop with, 1 (low) to 3 (high), in its prognosis."""
    if levels:
        stop_["prognosis"]["capacity1st"], stop_["prognosis"]["capacity2nd"] = levels


def highest_capacity(stops: list[dict]) -> tuple[int | None, int | None]:
    """The fullest any of these stops is expected to be, per class - /v1's journey value."""
    first = [s["prognosis"]["capacity1st"] for s in stops if s and s["prognosis"]["capacity1st"]]
    second = [s["prognosis"]["capacity2nd"] for s in stops if s and s["prognosis"]["capacity2nd"]]
    return max(first, default=None), max(second, default=None)


# The product classes of the SBB's HAFAS, which /v1 passed on as
# `categoryCode` until 2017 (the CATEGORY code of its answers): 0 high-speed
# trains, 1 InterCity and EuroCity, 2 InterRegio, 3 regional trains, 4 boats,
# 5 S-Bahn, 6 buses, 7 cableways and rack railways, 8 special trains, 9 trams
# and metros. Read off the fixtures of the old application (TGV 0, IC 1, IR 2,
# RE 3, S 5, Bus and Tro 6, Tram and NFT 9) and the HAFAS class list.
CATEGORY_CODES = {
    **dict.fromkeys(("ICE", "TGV", "RJ", "RJX", "FR", "FA", "THA"), 0),
    **dict.fromkeys(("IC", "ICN", "EC", "EN", "NJ", "CNL"), 1),
    **dict.fromkeys(("IR", "IRE", "PE"), 2),
    **dict.fromkeys(("RE", "R", "D", "TER", "RB", "REX", "TE2", "RER"), 3),
    **dict.fromkeys(("BAT", "FAE", "BAV"), 4),
    **dict.fromkeys(("S", "SN"), 5),
    **dict.fromkeys(("B", "BN", "BP", "CAR", "EXB", "EV", "NFB", "KB", "TX", "RUB"), 6),
    **dict.fromkeys(("FUN", "PB", "GB", "SL", "ASC", "CC", "ZB"), 7),
    **dict.fromkeys(("EXT", "ARZ", "AT", "VAE"), 8),
    **dict.fromkeys(("T", "NFT", "M"), 9),
}


def category_code(category: str | None) -> int | None:
    """`IC` -> 1: the HAFAS product class /v1 gave as `categoryCode`; None if unknown."""
    return CATEGORY_CODES.get((category or "").strip().upper())
