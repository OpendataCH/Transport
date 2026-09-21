"""What /v2 answers with.

Every field is always present. Where /v1 lets keys appear and vanish depending
on what the upstream happened to send, /v2 states the shape once and uses
`null` for "not known" - a client can then read a field without asking whether
it exists.
"""

from typing import Literal

from pydantic import BaseModel, Field

# The means of transport a station is served by, as search.ch names them in its
# icon classes. The same five the /v1 shape knows; anything else is null rather
# than invented.
Category = Literal["train", "tram", "bus", "ship", "cableway"]

LocationKind = Literal["station", "address"]


class Coordinate(BaseModel):
    """A point in WGS84, named rather than numbered.

    /v1 calls latitude `x` and longitude `y`, which is the wrong way round for
    anyone who has seen a coordinate pair before, and then computes both from
    the Swiss grid values with an approximation. The upstream answer carries
    proper WGS84 degrees already, so /v2 passes those through: fewer steps,
    smaller error, and names that say which is which.
    """

    lat: float = Field(description="Latitude in degrees.", examples=[46.948823])
    lon: float = Field(description="Longitude in degrees.", examples=[7.439123])


class Location(BaseModel):
    """A place one can search for: a stop, or a street address near one."""

    type: LocationKind = Field(description="What kind of place this is.")
    id: str | None = Field(
        description="The stop identifier, as used by `station=` elsewhere. Addresses have none."
    )
    name: str = Field(description="The name as search.ch spells it.")
    coordinate: Coordinate | None = Field(
        description="Where it is, or null when the upstream gives no position."
    )
    distance: float | None = Field(
        description="Metres from the searched point. Null unless the search was by coordinate."
    )
    category: Category | None = Field(
        description="Means of transport serving the stop, where known."
    )


class LocationsResponse(BaseModel):
    """The answer of `/v2/locations`.

    Called `locations`, not `stations`: the list has always contained addresses
    too, and /v1 calling them stations is one of the small untruths this
    version is free to drop.
    """

    locations: list[Location]
