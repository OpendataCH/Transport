"""`/v2/locations` - the location search, in the shape of `/v1`.

Same endpoint, same parameters, same JSON. What is different is underneath: one
upstream call to `completion.json`, and a mapping small enough to read in one
sitting.

The mapping is written against the PHP it replaces, oddities included, because
every one of them is either load-bearing for a client or indistinguishable from
one. They are named where they sit.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from .coordinates import lv03_to_wgs84
from .models import Errors, LocationsResponse
from .upstream import ClientIdentity, Upstream

router = APIRouter()

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


def get_upstream(request: Request) -> Upstream:
    """The shared connection pool, as a seam a test can replace."""
    return Upstream(request.app.state.http)


@router.get(
    "/locations",
    summary="Search for stations and locations",
    response_model=LocationsResponse,
    responses={429: {"model": Errors, "description": "search.ch is rate limiting."}},
)
async def search_locations(
    upstream: Annotated[Upstream, Depends(get_upstream)],
    identity: Annotated[ClientIdentity, Depends(ClientIdentity.of)],
    query: Annotated[
        str | None,
        Query(description="Location name to search for (e.g. `Bern`)."),
    ] = None,
    x: Annotated[
        str | None,
        Query(description="Latitude to search around (e.g. `47.476001`). Requires `y`."),
    ] = None,
    y: Annotated[
        str | None,
        Query(description="Longitude to search around (e.g. `8.306130`). Requires `x`."),
    ] = None,
    type: Annotated[  # noqa: A002 - the name is part of the /v1 contract
        str | None,
        Query(
            description="Accepted and ignored. The upstream completion "
            "endpoint has no type filter, so `/v1` has never narrowed "
            "anything with it either.",
        ),
    ] = None,
    key: Annotated[
        str | None,
        Query(
            description="A search.ch API key, forwarded unchanged. Without "
            "one, the caller's IP address is what search.ch rate limits on.",
        ),
    ] = None,
) -> Any:
    """Find locations by name, or the locations nearest a coordinate.

    Either `query`, or both `x` and `y`. Given neither, the answer is an empty
    list rather than an error - as in `/v1`, where a client that has always
    received `{"stations": []}` for a half-filled form would break on a 400.
    """
    stations: list[dict] = []

    if _set(query) or (_set(x) and _set(y)):
        entries = await upstream.completion(
            term=query,
            latlon=f"{x},{y}" if _set(x) and _set(y) else None,
            identity=identity,
        )
        stations = [to_station(entry) for entry in entries]

    return JSONResponse(content={"stations": stations})


def _set(value: str | None) -> bool:
    """PHP truthiness, because that is what decides this in `/v1`.

    `if ($query || ($x && $y))` treats an empty string and the string `"0"` as
    absent. A coordinate of exactly zero is in the Gulf of Guinea, so the
    second case has never mattered - but it is what the old endpoint does, and
    the differential test compares answers, not intentions.
    """
    return value is not None and value != "" and value != "0"


def to_station(entry: dict) -> dict:
    """Map one entry of `completion.json` into the /v1 location shape.

    The key order is the order of the PHP properties, and every key is present
    with `null` where /v1 has null - with one exception, `icon`, which /v1
    leaves out entirely when the upstream sends no icon class. That asymmetry
    is deliberate here; it is the "null versus missing" trap the plan names,
    and reproducing it is cheaper than finding out which client depends on it.
    """
    is_address = bool(entry.get("isaddress"))

    station: dict[str, Any] = {
        "id": _id(entry, is_address),
        "name": _name(entry),
        # Never set on this path: the score comes from the HAFAS answer, which
        # has not been asked since the switch to search.ch.
        "score": None,
        "coordinate": _coordinate(entry),
        "distance": entry["dist"] if "dist" in entry else None,
    }

    # Addresses are a different class in the PHP and never carry an icon, not
    # even a null one.
    if not is_address and "iconclass" in entry:
        station["icon"] = ICONS.get(entry["iconclass"])

    return station


def _id(entry: dict, is_address: bool) -> str | None:
    """The identifier, in the precedence the PHP applies by assigning in turn."""
    terminal = entry.get("terminal") or {}
    if is_address:
        # An address only ever picks up an id from a terminal.
        return _as_id(terminal.get("id"))
    for candidate in (terminal.get("id"), entry.get("stopid"), entry.get("id")):
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
