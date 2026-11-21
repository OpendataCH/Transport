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


class Prognosis(BaseModel):
    """The real-time picture of a stop, such as the upstream gives it."""

    platform: str | None = Field(description="Only ever null on this path.")
    arrival: str | None = Field(
        description="Expected arrival, ISO 8601 with a `+0100`-style offset. "
        "**Dated now** when the stop has no scheduled arrival - a quirk of "
        "/v1 that is reproduced here on purpose."
    )
    departure: str | None = Field(description="Expected departure, same format.")
    capacity1st: int | None = Field(
        description="Expected occupancy in first class: 1 low, 2 medium, 3 high. "
        "From the railways' forecast (SBB, BLS, SOB, Thurbo, zb trains); null otherwise."
    )
    capacity2nd: int | None = Field(description="The same for second class.")


class Stop(BaseModel):
    """One checkpoint of a journey."""

    station: Location | None = Field(
        description="Deprecated in /v1's own documentation, and still sent."
    )
    arrival: str | None = Field(description="ISO 8601 with a `+0100`-style offset.")
    arrivalTimestamp: int | None = Field(description="The same moment, in seconds.")  # noqa: N815
    departure: str | None
    departureTimestamp: int | None  # noqa: N815
    delay: float | None = Field(description="Minutes late, from the prognosis.")
    platform: str | None
    prognosis: Prognosis
    realtimeAvailability: str | None = Field(  # noqa: N815
        description="Only ever null on this path; it came from HAFAS."
    )
    location: Location = Field(
        description="Built from the same upstream object as `station` but by "
        "different rules, so the two can disagree."
    )


class Journey(BaseModel):
    """A line, and every stop of it the upstream mentions."""

    name: str | None
    category: str | None
    subcategory: str | None = Field(description="Only ever null on this path.")
    categoryCode: int | None = Field(  # noqa: N815
        description="The product class, as HAFAS numbered it: 0 high-speed train, "
        "1 InterCity/EuroCity, 2 InterRegio, 3 regional train, 4 boat, 5 S-Bahn, "
        "6 bus, 7 cableway, 8 special train, 9 tram or metro; null if unknown."
    )
    number: str | None
    operator: str | None
    to: str | None = Field(description="The final destination of the line.")
    passList: list[Stop]  # noqa: N815
    capacity1st: int | None = Field(
        description="Expected occupancy in first class: 1 low, 2 medium, 3 high. "
        "From the railways' forecast (SBB, BLS, SOB, Thurbo, zb trains); null otherwise."
    )
    capacity2nd: int | None = Field(description="The same for second class.")


class StationBoardJourney(Journey):
    """A line of a station board: a journey, plus the stop it makes here."""

    stop: Stop
    cancelled: bool | None = Field(
        default=None,
        description="Only with `showCancelled=1`: true when the journey is cancelled "
        "or passes this stop without calling.",
    )


class StationBoardResponse(BaseModel):
    """The answer of `/v2/stationboard`."""

    station: Location | None = Field(description="Null when no stop was asked for.")
    stationboard: list[StationBoardJourney]


class Walk(BaseModel):
    """How long a section is walked for, when it is walked."""

    duration: int | str | None = Field(
        description="Seconds, as search.ch gives them; null when it does not know."
    )


class Rental(BaseModel):
    """A shared bike, scooter or car taken for a section (only with `sharedMobility=1`)."""

    provider: str | None = Field(description="Who rents it out, e.g. `PubliBike`.")
    vehicle: str | None = Field(
        description="GBFS form factor: `bicycle`, `cargo_bicycle`, `scooter_standing`, `car` …"
    )
    propulsion: str | None = Field(description="`human`, `electric_assist`, `electric` …")
    from_station: str | None = Field(description="Where it is picked up, for a station system.")
    to_station: str | None = Field(description="Where it is left, for a station system.")
    url: str | None = Field(description="Where to book it, when the provider gives one.")


class Geometry(BaseModel):
    """The line a section follows on a map (only with `geometry=1`)."""

    polyline: str = Field(description="Encoded polyline, Google's algorithm.")
    precision: int = Field(description="Decimals of each coordinate in `polyline`, e.g. 6.")
    levels: list[float] | None = Field(
        default=None,
        description="Lowest and highest floor a walk reaches inside a station, 0 at street "
        "level; absent when it stays at street level.",
    )


class Section(BaseModel):
    """One leg of a connection: a vehicle, or a walk."""

    journey: Journey | None = Field(description="Null for a walk.")
    walk: Walk | None = Field(
        description="Null for anything with a vehicle. A shared vehicle's section is a walk "
        "with its duration, and says what it is in `rental`."
    )
    rental: Rental | None = Field(
        default=None, description="Only on a section with a shared vehicle (`sharedMobility=1`)."
    )
    departure: Stop
    arrival: Stop | None = Field(description="Null on a leg the upstream does not end.")
    geometry: Geometry | None = Field(
        default=None,
        description="Only with `geometry=1`: the line on a map. A walk follows the streets; "
        "a ride runs straight from stop to stop.",
    )


class Connection(BaseModel):
    """One way of getting from A to B."""

    from_: Stop | None = Field(alias="from", description="Where the journey starts.")
    to: Stop | None
    duration: str = Field(
        description="`00d00:43:00` - a literal zero, the days, `d`, then the clock.",
        examples=["00d00:43:00"],
    )
    transfers: int
    service: None = Field(description="Only ever null on this path; it came from HAFAS.")
    products: list[str] = Field(description="The lines used, in order.")
    capacity1st: int | None = Field(
        description="Expected occupancy in first class: 1 low, 2 medium, 3 high. "
        "From the railways' forecast (SBB, BLS, SOB, Thurbo, zb trains); null otherwise."
    )
    capacity2nd: int | None = Field(description="The same for second class.")
    sections: list[Section] | None = Field(
        description="Null - not an empty list - when no leg says what it is."
    )


class Stations(BaseModel):
    """The places the query resolved to, each as a list of one."""

    from_: list[Location] = Field(alias="from")
    to: list[Location]


class ConnectionsResponse(BaseModel):
    """The answer of `/v2/connections`."""

    connections: list[Connection]
    from_: Location | None = Field(alias="from", description="Departure of the search.")
    to: Location | None = Field(description="Arrival of the search.")
    stations: Stations


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
