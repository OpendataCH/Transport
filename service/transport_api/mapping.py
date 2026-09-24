"""Turning search.ch answers into the entities of /v1.

This was the PHP application's `lib/Transport/Entity` tree, read once and
written down as functions. Everything here is deliberate reproduction, including
the parts that are plainly wrong: /v1 must answer as it always has, so a fixed
bug would be a difference every unattended client might notice.

The oddities are named where they sit. The two that will surprise a reader
most:

- `station` and `location` on a stop are built from the *same* upstream object
  by two different rules, so they routinely disagree;
- a prognosis whose scheduled time is missing is dated **now**, because the PHP
  constructs a date from null and PHP reads that as the current moment.
"""

from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from .coordinates import lv03_to_wgs84
from .query import isset

ZURICH = ZoneInfo("Europe/Zurich")

# search.ch names the means of transport in a CSS class. /v1 knows these five
# and answers null for anything else - including addresses, whose class is
# `sl-icon-type-adr`.
ICONS = {
    "sl-icon-type-train": "train",
    "sl-icon-type-tram": "tram",
    "sl-icon-type-funicular": "cableway",
    "sl-icon-type-bus": "bus",
    "sl-icon-type-ship": "ship",
}


# The old transportation names, and what search.ch calls them now. /v1 accepts
# both and translates on the way out.
DEPRECATED_TYPES = {
    "ice_tgv_rj": "train",
    "ec_ic": "train",
    "ir": "train",
    "re_d": "train",
    "ship": "ship",
    "s_sn_r": "train",
    "bus": "bus",
    "cableway": "cableway",
    "arz_ext": "train",
    "tramway_underground": "tram",
    "tramway": "tram",
    "direct": "train",
    "direct_sleeper": "train",
    "direct_couchette": "train",
}


def transportation_types(transportations: list[str] | None) -> str | None:
    """The comma-separated list search.ch wants, or nothing at all.

    `all` - the default - means the filter is left out entirely rather than
    sent as every value.
    """
    if not transportations or transportations[0] == "all":
        return None

    translated = []
    for transportation in transportations:
        name = DEPRECATED_TYPES.get(transportation, transportation)
        if name not in translated:
            translated.append(name)
    return ",".join(translated)


# --------------------------------------------------------------------------
# Locations
# --------------------------------------------------------------------------


def location_of(entry: dict) -> dict:
    """`LocationFactory::createFromJson` - an address or a station."""
    return _location(entry, is_address=bool(entry.get("isaddress")))


def station_of(entry: dict) -> dict:
    """`Station::createStationFromJson`, applied whatever the entry is.

    A stop's `station` goes through this even when the entry says it is an
    address, while its `location` goes through the factory above. That is why
    the two fields can describe the same thing differently.
    """
    return _location(entry, is_address=False)


def _location(entry: dict, *, is_address: bool) -> dict:
    """The location shape: id, name, score, coordinate, distance, [icon].

    Every key is present with `null` where /v1 has null - with one exception,
    `icon`, which /v1 leaves out entirely when the upstream sends no icon
    class. That asymmetry is the "null versus missing" trap the plan names, and
    reproducing it is cheaper than finding out which client depends on it.
    """
    location: dict[str, Any] = {
        "id": _location_id(entry, is_address),
        "name": _name(entry),
        # Never set on this path: the score comes from the HAFAS answer, which
        # has not been asked since the switch to search.ch.
        "score": None,
        "coordinate": _coordinate(entry),
        "distance": entry["dist"] if isset(entry, "dist") else None,
    }

    # Addresses are a different class in the PHP and never carry an icon, not
    # even a null one.
    if not is_address and isset(entry, "iconclass"):
        location["icon"] = ICONS.get(entry["iconclass"])

    return location


def _location_id(entry: dict, is_address: bool) -> str | None:
    """The identifier, in the precedence the PHP applies by assigning in turn."""
    terminal = entry.get("terminal")
    terminal_id = terminal.get("id") if isinstance(terminal, dict) else None
    if is_address:
        # An address only ever picks up an id from a terminal.
        return _as_id(terminal_id)
    for candidate in (terminal_id, entry.get("stopid"), entry.get("id")):
        if candidate is not None:
            return _as_id(candidate)
    return None


def _as_id(value: Any) -> str | None:
    return None if value is None else str(value)


def _name(entry: dict) -> str | None:
    """`name` beats `label` beats `text` - the order the PHP overwrites in."""
    for field in ("name", "label", "text"):
        if entry.get(field) is not None:
            return entry[field]
    return None


def _coordinate(entry: dict) -> dict:
    """Always an object, even when there is nothing to put in it."""
    if entry.get("x") is None or entry.get("y") is None:
        return {"type": "WGS84", "x": None, "y": None}

    lat, lon = lv03_to_wgs84(int(entry["x"]), int(entry["y"]))
    return {"type": "WGS84", "x": lat, "y": lon}


# --------------------------------------------------------------------------
# Times
# --------------------------------------------------------------------------


def parse_time(value: str) -> datetime:
    """`2016-12-23 14:30:00` and the like, in Zurich time.

    An empty string is *now*, because that is what PHP's `new DateTime("")`
    makes of it - and search.ch does send empty times.
    """
    if value == "":
        return datetime.now(ZURICH).replace(microsecond=0)
    return datetime.fromisoformat(value).replace(tzinfo=ZURICH)


def iso(moment: datetime) -> str:
    """The format `/v1` emits: PHP's `DateTime::ISO8601`.

    `2016-12-23T14:30:00+0100` - note the offset without a colon. That constant
    predates RFC 3339 and is not quite ISO 8601 either, which is why it must be
    written out here rather than left to `isoformat()`.
    """
    return moment.strftime("%Y-%m-%dT%H:%M:%S%z")


def php_int(value: Any) -> int:
    """PHP's `(int)` cast of a string: the leading number, or zero.

    Delays arrive as `"+1"`, `"+0"`, and occasionally as something that is not
    a number at all.
    """
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int | float):
        return int(value)
    text = str(value).strip()
    digits = ""
    for index, character in enumerate(text):
        if character in "+-" and index == 0:
            digits += character
        elif character.isdigit():
            digits += character
        else:
            break
    try:
        return int(digits)
    except ValueError:
        return 0


# --------------------------------------------------------------------------
# Stops, prognoses, journeys
# --------------------------------------------------------------------------


def stop_of(entry: dict) -> dict:
    """`Stop::createFromJson` - one checkpoint of a journey."""
    arrival = _first_time(entry, ("arrival", "arr"))
    departure = _first_time(entry, ("departure", "dep", "time"))

    prognosis = _prognosis_of(entry, arrival, departure)

    return {
        # Deprecated in /v1's own documentation, and still sent.
        "station": station_of(entry),
        "arrival": iso(arrival) if arrival else None,
        "arrivalTimestamp": int(arrival.timestamp()) if arrival else None,
        "departure": iso(departure) if departure else None,
        "departureTimestamp": int(departure.timestamp()) if departure else None,
        "delay": _delay(prognosis, arrival, departure),
        "platform": entry.get("track"),
        "prognosis": prognosis,
        # Only ever set from the HAFAS answer, which is no longer asked.
        "realtimeAvailability": None,
        "location": location_of(entry),
    }


def _first_time(entry: dict, fields: tuple[str, ...]) -> datetime | None:
    """The *last* of these fields that is present wins.

    The PHP assigns them in turn without an else, so `time` overwrites `dep`
    overwrites `departure`.
    """
    found = None
    for field in fields:
        if isset(entry, field):
            found = parse_time(entry[field])
    return found


def _prognosis_of(entry: dict, arrival: datetime | None, departure: datetime | None) -> dict:
    """`Prognosis::createFromJson` - the real-time picture, such as it is."""
    prognosis: dict[str, Any] = {
        "platform": None,
        "arrival": None,
        "departure": None,
        "capacity1st": None,
        "capacity2nd": None,
    }

    if isset(entry, "arr_delay"):
        prognosis["arrival"] = iso(_delayed(arrival, php_int(entry["arr_delay"])))
    if isset(entry, "dep_delay"):
        prognosis["departure"] = iso(_delayed(departure, php_int(entry["dep_delay"])))

    return prognosis


def _delayed(scheduled: datetime | None, minutes: int) -> datetime:
    """Scheduled time plus the delay - or *now*, when there is no scheduled time.

    The PHP writes `new \\DateTime($stop->arrival)` and PHP reads a null there
    as "now". It shows: ask a station board for departures and the head stop,
    which has no arrival time, comes back with a prognosis dated this very
    second. It is wrong, it is live in production, and it is reproduced here -
    with the consequence that this one field cannot be compared between two
    requests, only within one.
    """
    # The delay is added whether or not there was a time to add it to. A
    # departure board's head stop has no arrival, so its arrival prognosis
    # comes back as "now plus the delay" - five minutes into the future of the
    # request, every time. Leaving the delay off in that case was a bug in this
    # port, and one that only replaying real traffic showed.
    base = scheduled if scheduled is not None else datetime.now(ZURICH).replace(microsecond=0)

    # A negative delay is read and then ignored: only a positive one moves the
    # time. So an early departure is announced as punctual.
    return base + timedelta(minutes=minutes) if minutes > 0 else base


def _delay(
    prognosis: dict, arrival: datetime | None, departure: datetime | None
) -> int | float | None:
    """Minutes late, from the prognosis against the scheduled time.

    Departure wins over arrival when both are there, because the PHP computes
    the arrival delay first and then overwrites it.
    """
    delay = None
    if prognosis["arrival"] and arrival:
        delay = _minutes(parse_time(prognosis["arrival"]), arrival)
    if prognosis["departure"] and departure:
        delay = _minutes(parse_time(prognosis["departure"]), departure)
    return delay


def _minutes(later: datetime, earlier: datetime) -> int | float:
    """Whole minutes stay integers, as PHP's division leaves them."""
    seconds = int(later.timestamp()) - int(earlier.timestamp())
    return seconds // 60 if seconds % 60 == 0 else seconds / 60


def journey_of(entry: dict) -> dict:
    """`Journey::createFromJson` - the line, and every stop it is known to make."""
    name = None
    number = None
    category = None

    if isset(entry, "number"):
        name = number = entry["number"]
    if isset(entry, "*Z"):
        name = number = entry["*Z"]
    if isset(entry, "*L"):
        number = entry["*L"]
    if isset(entry, "line"):
        category = entry["line"]
    if isset(entry, "*G"):
        category = entry["*G"]

    terminal = entry.get("terminal")
    if isinstance(terminal, dict):
        to = terminal.get("name")
    else:
        to = terminal

    return {
        "name": name,
        "category": category,
        # Neither is ever set on this path; both came from the HAFAS answer.
        "subcategory": None,
        "categoryCode": None,
        "number": number,
        "operator": entry.get("operator"),
        "to": to,
        "passList": _pass_list(entry),
        "capacity1st": None,
        "capacity2nd": None,
    }


def _pass_list(entry: dict) -> list[dict]:
    """The journey's own stop first, then whatever the upstream lists."""
    stops = [stop_of(entry)]
    for field in ("stops", "subsequent_stops"):
        for stop in entry.get(field) or []:
            stops.append(stop_of(stop))
    if entry.get("exit"):
        stops.append(stop_of(entry["exit"]))
    return stops


def station_board_journey_of(entry: dict) -> dict:
    """One line of a station board: a journey, with the stop it makes here.

    The key order is the PHP's: `stop` first, then the journey's own fields.
    """
    journey = journey_of(entry)
    return {"stop": stop_of(entry), **journey}


# --------------------------------------------------------------------------
# Connections
# --------------------------------------------------------------------------


def connection_of(entry: dict) -> dict:
    """`Connection::createFromJson` - one way of getting from A to B.

    A leg is a stop with what happens after it. The first leg is the departure,
    the last one is nothing but an arrival, and everything in between is a
    change. /v1 reads them twice over: once as the two ends of the connection,
    once as its sections.
    """
    legs = entry.get("legs") or []

    origin = stop_of(legs[0]) if legs else None
    destination = stop_of(legs[-1]) if legs else None

    # The last leg carries no platform of its own; the one before it knows
    # where the train got in and out.
    if destination is not None and not destination["platform"] and len(legs) >= 2:
        exit_ = legs[-2].get("exit") or {}
        if isset(exit_, "track"):
            # `isset`, not "is it worth having": search.ch sends an empty
            # string for a stop without a platform, and /v1 copies it. A null
            # here instead of an empty string is a difference in the answer.
            destination["platform"] = exit_["track"]

    return {
        "from": origin,
        "to": destination,
        "duration": duration_of(entry.get("duration") or 0),
        # Only a leg that says what it is counts. The last leg of a
        # connection is a bare arrival with no type, and counting it would
        # add a change that nobody makes.
        "transfers": max(sum(1 for leg in legs if leg.get("type", "walk") != "walk") - 1, 0),
        # Set from the HAFAS answer only, so always null here - and null, not
        # an empty object.
        "service": None,
        "products": [leg["line"] for leg in legs if isset(leg, "line")],
        "capacity1st": None,
        "capacity2nd": None,
        "sections": _sections(legs),
    }


def _sections(legs: list[dict]) -> list[dict] | None:
    """Only legs that say what they are become sections.

    A connection whose legs carry no `type` at all therefore has `sections`
    null rather than an empty list - the PHP never creates the array.
    """
    sections = [section_of(leg) for leg in legs if isset(leg, "type")]
    return sections or None


def section_of(leg: dict) -> dict:
    """`Section::createFromJson` - one leg, as /v1 shapes it."""
    return {
        "journey": journey_of(leg) if isset(leg, "tripid") else None,
        "walk": {"duration": leg.get("normal_time")} if leg.get("type") == "walk" else None,
        "departure": stop_of(leg),
        "arrival": stop_of(leg["exit"]) if leg.get("exit") else None,
    }


def duration_of(seconds: int) -> str:
    """`00d00:43:00` - PHP's `gmdate("0z\\dH:i:s")`.

    A literal zero, then the day of the year (zero-based, so a duration under
    24 hours gives `0`), then `d`, then the clock. Two days look like `02d`;
    ten look like `010d`, because `z` is not padded. Nobody would design this,
    and it is what every client parses.
    """
    seconds = int(seconds)
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    return f"0{days}d{hours:02d}:{minutes:02d}:{secs:02d}"
