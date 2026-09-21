"""`/v2/stationboard` - the departures (or arrivals) of one stop.

Two million requests a day and a narrow shape: one upstream call to
`stationboard.json`, one station and a list of journeys. As everywhere in this
service, the answer is `/v1`'s, oddities included; the mapping itself lives in
`mapping.py`.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, PlainTextResponse

from . import errors
from .mapping import ZURICH, station_board_journey_of, station_of, transportation_types, truthy
from .models import Errors, StationBoardResponse
from .upstream import ClientIdentity, Upstream, get_upstream

router = APIRouter()

# The default when nobody says otherwise, and the ceiling above which /v1
# refuses. Both are the PHP's.
DEFAULT_LIMIT = "40"
MAX_LIMIT = 420


@router.get(
    "/stationboard",
    summary="Get station board",
    response_model=StationBoardResponse,
    responses={
        400: {"description": "`limit` above 420.", "content": {"text/plain": {}}},
        429: {"model": Errors, "description": "search.ch is rate limiting."},
    },
)
async def station_board(
    upstream: Annotated[Upstream, Depends(get_upstream)],
    identity: Annotated[ClientIdentity, Depends(ClientIdentity.of)],
    station: Annotated[
        str | None,
        Query(description="The stop to report on (e.g. `Aarau`)."),
    ] = None,
    id: Annotated[  # noqa: A002 - the name is part of the /v1 contract
        str | None,
        Query(
            description="The stop id, as an alternative to `station`. One of "
            "the two is required; `station` takes precedence when both are "
            "given."
        ),
    ] = None,
    limit: Annotated[
        str,
        Query(
            description="Number of departures to return, at most 420. Not a "
            "hard limit: connections leaving at the same minute as the last "
            "one are all returned."
        ),
    ] = DEFAULT_LIMIT,
    transportations: Annotated[
        list[str] | None,
        Query(
            alias="transportations[]",
            description="Means of transport: one or more of `train`, `tram`, "
            "`ship`, `bus`, `cableway`. Array notation "
            "(`transportations[]=tram&transportations[]=bus`).",
        ),
    ] = None,
    transportations_single: Annotated[
        list[str] | None,
        Query(
            alias="transportations",
            description="The same, without the brackets. PHP folds both "
            "spellings into one parameter, so /v1 accepts either.",
        ),
    ] = None,
    datetime_: Annotated[
        str | None,
        Query(
            alias="datetime",
            description="Date and time, `YYYY-MM-DD hh:mm`. Defaults to now.",
        ),
    ] = None,
    date: Annotated[
        str | None,
        Query(description="Undocumented in /v1, accepted, and takes precedence over `datetime`."),
    ] = None,
    type: Annotated[  # noqa: A002 - the name is part of the /v1 contract
        str | None,
        Query(description="`departure` (default) or `arrival`."),
    ] = None,
    key: Annotated[
        str | None,
        Query(description="A search.ch API key, forwarded unchanged."),
    ] = None,
) -> Any:
    """The next journeys leaving from (or arriving at) one stop.

    Without a stop the answer is an empty board rather than an error, as in
    `/v1`.
    """
    if _over_the_limit(limit):
        # Plain text, not the error envelope. /v1 answers this one with a bare
        # string, and a client that has learned to read it would not recognise
        # a JSON document in its place.
        return PlainTextResponse("Invalid value for Parameter `limit`.", status_code=400)

    stop = station if truthy(station) else id
    if not truthy(stop):
        return JSONResponse(content={"station": None, "stationboard": []})

    when = _when(date or datetime_)

    payload = await upstream.stationboard(
        stop=stop,
        when=when,
        mode="arrival" if type == "arrival" else "depart",
        limit=limit,
        transportation_types=transportation_types(transportations or transportations_single),
        identity=identity,
    )

    board_station = station_of(payload["stop"]) if payload.get("stop") is not None else None

    journeys = []
    for connection in payload.get("connections") or []:
        journey = station_board_journey_of(connection)
        # The board's own station replaces whatever the connection said about
        # this stop - and only on the journey's `stop`, not in its passList,
        # which is why the two disagree.
        journey["stop"]["station"] = board_station
        journeys.append(journey)

    return JSONResponse(content={"station": board_station, "stationboard": journeys})


def _over_the_limit(limit: str) -> bool:
    """`$limit > 420`, with PHP 8's comparison rules.

    A numeric string is compared as a number. A non-numeric one makes PHP cast
    the *number* to a string and compare the two as text - so `limit=abc` is
    "greater" than `420` and refused, while `limit=4abc` is not. Silly, and
    what the endpoint does.
    """
    try:
        return float(limit) > MAX_LIMIT
    except ValueError:
        return limit > str(MAX_LIMIT)


def _when(given: str | None) -> datetime:
    """The moment to ask about: what was given, or now, in Zurich."""
    if not given:
        return datetime.now(ZURICH)
    try:
        return datetime.fromisoformat(given).replace(tzinfo=ZURICH)
    except ValueError:
        pass
    for pattern in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%H:%M", "%H:%M:%S"):
        try:
            parsed = datetime.strptime(given, pattern)
        except ValueError:
            continue
        if pattern in ("%H:%M", "%H:%M:%S"):
            today = datetime.now(ZURICH)
            parsed = parsed.replace(year=today.year, month=today.month, day=today.day)
        return parsed.replace(tzinfo=ZURICH)

    # /v1 lets the DateTime constructor throw here, which its error handler
    # turns into a 500 naming the string it could not read.
    raise errors.ApiError(500, f"DateTime::__construct(): Failed to parse time string ({given})")
