"""Addresses and points of interest, from the router's place search.

The timetable knows stops only. /v1 has always also found addresses
("Neufeldstrasse 101, Bern") and points of interest, and taken them as the
start or end of a connection. MOTIS indexes the Swiss OpenStreetMap extract
for its own place search (`geocoding: true`); asking it keeps every query on
this server, and its router walks from such a point along the streets to the
stops nearby.
"""

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from .. import errors
from .names import normalize

if TYPE_CHECKING:
    from .router import Motis

# A house number: digits, perhaps a letter ("4c"). Names of stops have few.
HOUSE_NUMBER = re.compile(r"\b(\d+(?:\.\d+)?[a-zA-Z]?)\b")

# What /v1 calls the kinds, and what the router calls them.
KINDS = {"address": "ADDRESS", "poi": "PLACE"}

# The administrative level of a Swiss municipality in OpenStreetMap.
MUNICIPALITY = 8

# "47.3769,8.5417": a point in WGS84 degrees, latitude first.
POINT = re.compile(r"^\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$")


@dataclass
class Place:
    """An address or point of interest: a name as /v1 writes it, and where it is."""

    name: str
    lat: float
    lon: float
    kind: str
    house_number: str | None = None
    towns: tuple[str, ...] = ()

    @property
    def coordinate(self) -> str:
        """The form the router takes for a place that is no stop."""
        return f"{self.lat},{self.lon}"


def point(text: str) -> tuple[float, float] | None:
    """The latitude and longitude `text` gives, when it is nothing but a coordinate.

    search.ch took `from=47.3769,8.5417` as a start of its own, and /v1 passed
    the parameter through - undocumented, but in use.
    """
    match = POINT.match(text)
    if match is None:
        return None
    lat, lon = float(match.group(1)), float(match.group(2))
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None
    return lat, lon


def house_number(text: str) -> str | None:
    match = HOUSE_NUMBER.search(text)
    return match.group(1).lower() if match else None


async def search(
    motis: "Motis | None", text: str, kinds: tuple[str, ...], limit: int = 10
) -> list[Place]:
    """Places matching `text`, best first; empty without a router or a match."""
    if motis is None or not text.strip():
        return []
    params = {"text": text, "language": "de", "numResults": str(limit)}
    if len(kinds) == 1:
        params["type"] = KINDS[kinds[0]]
    try:
        matches = await motis.get("/api/v1/geocode", params)
    except errors.ApiError:
        return []
    wanted = {KINDS[kind] for kind in kinds}
    places = []
    for match in matches if isinstance(matches, list) else []:
        if match.get("type") not in wanted or match.get("lat") is None:
            continue
        places.append(
            Place(
                name=_name(match),
                lat=round(match["lat"], 6),
                lon=round(match["lon"], 6),
                kind="address" if match["type"] == "ADDRESS" else "poi",
                house_number=(match.get("houseNumber") or "").lower() or None,
                # The municipality and its parts - not the canton, which
                # shares its name with a town (Luzern, Bern, Zug …).
                towns=tuple(
                    normalize(a["name"])
                    for a in match.get("areas") or []
                    if a.get("name") and (a.get("adminLevel") or 0) >= MUNICIPALITY
                ),
            )
        )
    return _in_town(places, text)[:limit]


def _in_town(places: list[Place], text: str) -> list[Place]:
    """Only the places in the town a query names after its comma.

    "Bahnhofplatz 5, Luzern" means Luzern, however well a Bahnhofplatz 5
    elsewhere matches the street. An address in another town is dropped -
    no answer is better than a wrong one; a point of interest stays, after
    those in the town, since its name is what was asked for.
    """
    if "," not in text:
        return places
    town = normalize(re.sub(r"\b\d{4}\b", "", text.rsplit(",", 1)[1]))
    if not town:
        return places

    def here(place: Place) -> bool:
        return any(town == t or town in t.split() or t in town for t in place.towns if t)

    inside = [p for p in places if here(p)]
    outside = [p for p in places if not here(p) and p.kind == "poi"]
    return inside + outside


async def address(motis: "Motis | None", text: str) -> Place | None:
    """The address `text` names, when it names one with its house number."""
    number = house_number(text)
    if number is None:
        return None
    found = await search(motis, text, ("address",), limit=10)
    for place in found:
        if place.house_number == number:
            return place
    # "Weberstrasse 9.1": a number the map writes otherwise; the street in
    # the town asked for is closer than any stop of a similar name.
    for place in found:
        if place.house_number and place.house_number.split(".")[0] == number.split(".")[0]:
            return place
    return found[0] if found else None


def _name(match: dict) -> str:
    """`Bern, Neufeldstrasse 101` and `Bundeshaus, Bern`: town first for an
    address, last for a point of interest, as search.ch writes them."""
    town = _town(match.get("areas") or [])
    if match.get("type") == "ADDRESS":
        street = " ".join(p for p in (match.get("street"), match.get("houseNumber")) if p)
        street = street or match.get("name") or ""
        return f"{town}, {street}" if town else street
    name = match.get("name") or ""
    return f"{name}, {town}" if town and town not in name else name


def _town(areas: list[dict]) -> str | None:
    by_level = {area.get("adminLevel"): area.get("name") for area in areas}
    if MUNICIPALITY in by_level:
        return by_level[MUNICIPALITY]
    default = next((a.get("name") for a in areas if a.get("default")), None)
    return default


# How far the nearest address may be to be named for a coordinate.
NEAREST_ADDRESS_METRES = 250


async def nearest_address(motis: "Motis | None", lat: float, lon: float) -> Place | None:
    """The address nearest a coordinate, named as search.ch names it there.

    `Bubenbergplatz 4c, 3011 Bern`: street first and the postcode with the
    town - not the town first, as for a searched address. None without a
    router that has reverse geocoding, or without an address nearby.
    """
    if motis is None:
        return None
    try:
        matches = await motis.get(
            "/api/v1/reverse-geocode",
            {"place": f"{lat},{lon}", "type": "ADDRESS", "numResults": "1"},
        )
    except errors.ApiError:
        return None
    for match in matches if isinstance(matches, list) else []:
        if match.get("type") != "ADDRESS" or match.get("lat") is None:
            continue
        street = " ".join(p for p in (match.get("street"), match.get("houseNumber")) if p)
        town = " ".join(p for p in (match.get("zip"), _town(match.get("areas") or [])) if p)
        return Place(
            name=", ".join(p for p in (street or match.get("name"), town) if p),
            lat=round(match["lat"], 6),
            lon=round(match["lon"], 6),
            kind="address",
            house_number=(match.get("houseNumber") or "").lower() or None,
        )
    return None
