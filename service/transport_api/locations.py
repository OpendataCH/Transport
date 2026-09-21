"""`/v2/locations` - the location search, in the shape of `/v1`.

Same endpoint, same parameters, same JSON. What is different is underneath: one
upstream call to `completion.json`, and a mapping small enough to read in one
sitting.

The mapping is written against the PHP it replaces, oddities included, because
every one of them is either load-bearing for a client or indistinguishable from
one. They are named where they sit.
"""

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from .fields import Fields
from .mapping import location_of
from .models import Errors, LocationsResponse
from .query import truthy
from .upstream import ClientIdentity, Upstream, get_upstream

router = APIRouter()


@router.get(
    "/locations",
    summary="Search for stations and locations",
    response_model=LocationsResponse,
    responses={429: {"model": Errors, "description": "search.ch is rate limiting."}},
)
async def search_locations(
    upstream: Annotated[Upstream, Depends(get_upstream)],
    identity: Annotated[ClientIdentity, Depends(ClientIdentity.of)],
    fields: Annotated[Fields, Depends(Fields.of)],
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
    fields_: Annotated[
        list[str] | None,
        Query(
            alias="fields[]",
            description="Keep only these parts of the answer. A `/`-separated "
            "path of object keys; lists are transparent, so "
            "`connections/from/departure` reaches into every connection. "
            "A narrower path beats a broader one, and an object left with no "
            "keys comes back as `[]`.",
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

    if truthy(query) or (truthy(x) and truthy(y)):
        entries = await upstream.completion(
            term=query,
            latlon=f"{x},{y}" if truthy(x) and truthy(y) else None,
            identity=identity,
        )
        stations = [location_of(entry) for entry in entries]

    return JSONResponse(content=fields.apply({"stations": stations}))
