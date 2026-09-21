"""`/v2/locations` - search for stops and addresses.

One upstream call, one list out. The mapping is small enough to read in one
sitting, which is the point: everything that could surprise a reader is named
here rather than left in the shape of the data.
"""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query, Request, Response

from . import problems
from .models import Category, Coordinate, Location, LocationKind, LocationsResponse
from .upstream import ClientIdentity, Upstream

router = APIRouter()

# search.ch names the means of transport in a CSS class. These five are the
# ones with a meaning; anything else - including the address marker below -
# leaves `category` null rather than inventing a word for it.
CATEGORIES: dict[str, Category] = {
    "sl-icon-type-train": "train",
    "sl-icon-type-tram": "tram",
    "sl-icon-type-funicular": "cableway",
    "sl-icon-type-bus": "bus",
    "sl-icon-type-ship": "ship",
}

ADDRESS_ICON = "sl-icon-type-adr"

# A stop lookup is worth caching for an hour: the list of places served in
# Switzerland changes with the timetable, not with the minute. The departures
# of a single stop are a different matter and will say so themselves.
CACHE_CONTROL = "public, max-age=3600"


def get_upstream(request: Request) -> Upstream:
    """The shared connection pool, as a seam a test can replace."""
    return Upstream(request.app.state.http)


@router.get(
    "/locations",
    summary="Search for stops and addresses",
    response_model=LocationsResponse,
    responses={
        400: {"description": "Neither a query nor a complete coordinate."},
        429: {"description": "search.ch is rate limiting this caller."},
        502: {"description": "search.ch answered in a way this service cannot use."},
        504: {"description": "search.ch did not answer in time."},
    },
)
async def search_locations(
    response: Response,
    upstream: Annotated[Upstream, Depends(get_upstream)],
    identity: Annotated[ClientIdentity, Depends(ClientIdentity.of)],
    query: Annotated[
        str | None,
        Query(
            description="Name to search for, complete or not (e.g. `Bern`).",
            examples=["Bern"],
        ),
    ] = None,
    lat: Annotated[
        float | None,
        Query(
            ge=-90,
            le=90,
            description="Latitude to search around. Requires `lon`.",
            examples=[47.002347],
        ),
    ] = None,
    lon: Annotated[
        float | None,
        Query(
            ge=-180,
            le=180,
            description="Longitude to search around. Requires `lat`.",
            examples=[8.379934],
        ),
    ] = None,
    kind: Annotated[
        Literal["all", "station", "address"],
        Query(
            alias="type",
            description="Narrow the answer to one kind of place. Filtered "
            "here, not upstream, so it never changes which places are found - "
            "only which are returned.",
        ),
    ] = "all",
    key: Annotated[
        str | None,
        Query(
            description="A search.ch API key, forwarded unchanged. Without "
            "one, the caller's IP address is what search.ch rate limits on.",
        ),
    ] = None,
) -> LocationsResponse:
    """Find places by name, or the places nearest a coordinate.

    Either `query` or both `lat` and `lon`. /v1 answers an empty list when
    given neither, which reads as "nothing found" for what is really "nothing
    asked"; here it is a 400.
    """
    _validate(query, lat, lon)

    entries = await upstream.completion(
        term=query,
        latlon=f"{lat},{lon}" if lat is not None and lon is not None else None,
        identity=identity,
    )

    locations = [mapped for entry in entries if (mapped := to_location(entry))]
    if kind != "all":
        locations = [location for location in locations if location.type == kind]

    response.headers["Cache-Control"] = CACHE_CONTROL
    return LocationsResponse(locations=locations)


def _validate(query: str | None, lat: float | None, lon: float | None) -> None:
    if (lat is None) != (lon is None):
        raise problems.bad_request("lat and lon go together; give both or neither.")
    if not query and lat is None:
        raise problems.bad_request("Give either query, or lat and lon.")


def to_location(entry: dict) -> Location | None:
    """Map one entry of `completion.json`.

    Returns None for an entry with no name. That is not a place anyone can use,
    and passing it on as `"name": null` would make every client check.
    """
    name = entry.get("label") or entry.get("text") or entry.get("name")
    if not name:
        return None

    icon = entry.get("iconclass")
    is_address = bool(entry.get("isaddress")) or icon == ADDRESS_ICON
    kind: LocationKind = "address" if is_address else "station"

    return Location(
        type=kind,
        id=str(entry["id"]) if entry.get("id") else None,
        name=name,
        coordinate=_coordinate(entry),
        distance=float(entry["dist"]) if entry.get("dist") is not None else None,
        category=None if is_address else CATEGORIES.get(icon or ""),
    )


def _coordinate(entry: dict) -> Coordinate | None:
    """The WGS84 degrees the upstream already carries.

    /v1 ignores these and computes the pair from the Swiss grid values `x` and
    `y` with the swisstopo approximation, which lands a metre or so away. The
    numbers are therefore *not* identical between the two versions, and that is
    deliberate - see the compatibility layer, which keeps the old arithmetic.
    """
    lat, lon = entry.get("lat"), entry.get("lon")
    if lat is None or lon is None:
        return None
    return Coordinate(lat=float(lat), lon=float(lon))
