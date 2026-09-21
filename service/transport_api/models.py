"""The shapes /v2 answers with - the shapes of /v1.

`/v2` is the same API as `/v1`, served by a different implementation. Its
endpoints, parameters and JSON are the ones tens of thousands of unattended
clients already speak, which is what makes the two comparable request by
request - and what will let `/v1` be routed here once they have been proven
identical for long enough.

These models exist for the OpenAPI document. The route builds its answer as
plain data, because some of this shape cannot be expressed by a model: `icon`
is absent rather than null when the upstream sends no icon class, and a
distance stays the integer it arrived as. A test validates every mapped answer
against the models here, so the description cannot drift away from the thing.
"""

from pydantic import BaseModel, Field


class Coordinate(BaseModel):
    """A point, in the naming /v1 uses.

    `x` is the latitude and `y` the longitude - the other way round from what
    most people expect, and kept because changing it would break every client
    that reads them.

    Both are computed from the Swiss grid values with the swisstopo
    approximation, not taken from the WGS84 degrees the upstream also sends.
    The two differ by about a metre; see `coordinates.py`.
    """

    type: str = Field(description="Always `WGS84`.", examples=["WGS84"])
    x: float | None = Field(description="Latitude.", examples=[46.948832])
    y: float | None = Field(description="Longitude.", examples=[7.439136])


class Location(BaseModel):
    """A station, address or point of interest."""

    id: str | None = Field(description="The stop identifier. Null for an address.")
    name: str | None = Field(description="The name as search.ch spells it.")
    score: int | None = Field(
        description="Match quality. Always null on this path - the field is a "
        "leftover of the HAFAS era, kept because it has always been sent."
    )
    coordinate: Coordinate
    distance: float | None = Field(
        description="Metres from the searched point, when the search was by "
        "coordinate. Null otherwise."
    )
    icon: str | None = Field(
        None,
        description="One of `train`, `tram`, `bus`, `ship`, `cableway`; null "
        "for anything else. **Absent entirely** when the upstream entry "
        "carries no icon class at all.",
    )


class LocationsResponse(BaseModel):
    """The answer of `/v2/locations`.

    The key is `stations` although the list also carries addresses. That is how
    /v1 names it.
    """

    stations: list[Location]


class ErrorMessage(BaseModel):
    message: str


class Errors(BaseModel):
    """The error envelope of /v1, unchanged."""

    errors: list[ErrorMessage]


class ApiInfo(BaseModel):
    """What `/v2/` says about the API."""

    date: str = Field(description="Now, ISO 8601 with offset.")
    author: str
    version: str
