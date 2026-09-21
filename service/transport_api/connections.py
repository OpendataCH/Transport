"""`/v2/connections` - journeys from one place to another.

2.6 million requests a day, the deepest nesting, and the only endpoint with
arithmetic of its own: `/v1` asks search.ch for a page's worth of results and
then cuts the list itself. All of that is reproduced here, including the
parameters that are accepted and then never used.
"""

from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from .mapping import ZURICH, connection_of, location_of, transportation_types, truthy
from .models import ConnectionsResponse, Errors
from .upstream import ClientIdentity, Upstream, get_upstream

router = APIRouter()

DEFAULT_LIMIT = 4
DEFAULT_PAGE = 0

MAX_LIMIT = 16
MAX_PAGE = 10
MAX_VIA = 5

# search.ch is asked for everything up to the end of the requested page, and
# /v1 cuts the page out of that. Sixteen is where it stops asking.
WINDOW = 16


@router.get(
    "/connections",
    summary="Search connections",
    response_model=ConnectionsResponse,
    responses={
        400: {"model": Errors, "description": "A parameter is out of range."},
        429: {"model": Errors, "description": "search.ch is rate limiting."},
    },
)
async def search_connections(
    upstream: Annotated[Upstream, Depends(get_upstream)],
    identity: Annotated[ClientIdentity, Depends(ClientIdentity.of)],
    from_: Annotated[
        str | None,
        Query(alias="from", description="Where the journey starts (e.g. `Lausanne`)."),
    ] = None,
    to: Annotated[
        str | None,
        Query(description="Where it ends (e.g. `Genève`)."),
    ] = None,
    via: Annotated[
        list[str] | None,
        Query(
            alias="via[]",
            description="Up to five places to pass through. With more than "
            "one, array notation is required.",
        ),
    ] = None,
    via_single: Annotated[
        list[str] | None,
        Query(alias="via", description="The same, without the brackets."),
    ] = None,
    date: Annotated[
        str | None,
        Query(description="Date of the journey, `YYYY-MM-DD`."),
    ] = None,
    time: Annotated[
        str | None,
        Query(description="Time of the journey, `hh:mm`."),
    ] = None,
    datetime_: Annotated[
        str | None,
        Query(
            alias="datetime",
            description="Date and time in one, taking precedence over `date` and `time`.",
        ),
    ] = None,
    isArrivalTime: Annotated[  # noqa: N803 - the name is part of the /v1 contract
        str | None,
        Query(description="`1` or `true` if the given time is the arrival time."),
    ] = None,
    limit: Annotated[
        str | None,
        Query(description="1 - 16. Connections to return; the default is 4."),
    ] = None,
    page: Annotated[
        str | None,
        Query(description="0 - 10. Zero-based page of results."),
    ] = None,
    transportations: Annotated[
        list[str] | None,
        Query(alias="transportations[]", description="Means of transport to allow."),
    ] = None,
    transportations_single: Annotated[
        list[str] | None,
        Query(alias="transportations", description="The same, without the brackets."),
    ] = None,
    direct: Annotated[str | None, Query(description="Accepted and ignored on this path.")] = None,
    sleeper: Annotated[str | None, Query(description="Accepted and ignored on this path.")] = None,
    couchette: Annotated[
        str | None, Query(description="Accepted and ignored on this path.")
    ] = None,
    chouchette: Annotated[
        str | None,
        Query(description="A typo of `couchette` that /v1 accepts. Also ignored."),
    ] = None,
    bike: Annotated[str | None, Query(description="Accepted and ignored on this path.")] = None,
    accessibility: Annotated[
        str | None, Query(description="Accepted and ignored on this path.")
    ] = None,
    key: Annotated[
        str | None, Query(description="A search.ch API key, forwarded unchanged.")
    ] = None,
) -> Any:
    """The next connections from one place to another.

    `direct`, `sleeper`, `couchette`, `bike` and `accessibility` are declared
    because `/v1` declares them, and they do nothing: they only ever reached
    the HAFAS request, which is no longer made. Answering "unknown parameter"
    to a client that has always sent them would be a change of behaviour.
    """
    if not (truthy(from_) and truthy(to)):
        return JSONResponse(
            content={
                "connections": [],
                "from": None,
                "to": None,
                "stations": {"from": [], "to": []},
            }
        )

    places = via or via_single or []
    limit_value = _number(limit, DEFAULT_LIMIT)
    page_value = _number(page, DEFAULT_PAGE)

    problems = _validate(limit_value, page_value, places)
    if problems:
        # A list of strings, not of objects. /v1 uses a different error shape
        # here than for its exceptions, and both are in the wild.
        return JSONResponse(status_code=400, content={"errors": problems})

    arrival = _is_arrival_time(isArrivalTime)
    when = _when(datetime_, date, time)

    # Asking for arrival times shifts the window one page back, as in /v1.
    window_page = page_value - 1 if arrival else page_value

    payload = await upstream.route(
        origin=from_,
        destination=to,
        via=places,
        when=when,
        time_type="arrival" if arrival else "departure",
        num=(window_page + 1) * limit_value if window_page >= 0 else None,
        pre=abs(window_page) * limit_value if window_page < 0 else None,
        transportation_types=transportation_types(transportations or transportations_single),
        identity=identity,
    )

    connections = [connection_of(entry) for entry in payload.get("connections") or []]
    connections = _page(connections, limit_value, window_page)

    origin = destination = None
    stations: dict[str, list] = {"from": [], "to": []}
    points = payload.get("points")
    if points:
        origin = location_of(points[0])
        destination = location_of(points[1])
        stations = {"from": [origin], "to": [destination]}

    return JSONResponse(
        content={
            "connections": connections,
            "from": origin,
            "to": destination,
            "stations": stations,
        }
    )


def _page(connections: list[dict], limit: int, page: int) -> list[dict]:
    """The page /v1 cuts out of what search.ch sent.

    The upstream is asked for everything up to the end of the requested page,
    so the page is a slice of the answer. The offset is clamped into the first
    sixteen results, which is why a high page with a high limit quietly returns
    the tail of the window instead of an empty list.
    """
    offset = min(max(page * limit, 0), WINDOW - limit)
    return connections[offset : offset + limit]


def _validate(limit: int, page: int, via: list[str]) -> list[str]:
    problems = []
    if limit > MAX_LIMIT:
        problems.append(f"Maximal value of argument `limit` is {MAX_LIMIT}.")
    if page > MAX_PAGE:
        problems.append(f"Maximal value of argument `page` is {MAX_PAGE}.")
    if len(via) > MAX_VIA:
        problems.append(f"Invalid via count (max {MAX_VIA} allowed).")
    return problems


def _number(value: str | None, default: int) -> int:
    """A count, as PHP would read it: anything unreadable is the default."""
    if not truthy(value):
        return default
    try:
        return int(float(value))
    except ValueError:
        return default


def _is_arrival_time(value: str | None) -> bool:
    """`0`, `1`, `false`, `true` - and anything else leaves it alone."""
    return value in ("1", "true")


def _when(combined: str | None, date: str | None, time: str | None) -> datetime:
    """The moment to search from: `datetime`, or `date` and `time`, or now.

    Either half may be missing, and each falls back to the current day or the
    current minute on its own - which is what makes `time=23:50` without a date
    mean tonight.
    """
    now = datetime.now(ZURICH)

    if truthy(combined):
        parsed = _parse(combined)
        return parsed if parsed else now

    day = _parse(date) if truthy(date) else None
    clock = _parse(time, reference=day or now) if truthy(time) else None

    return (day or now).replace(
        hour=(clock or now).hour,
        minute=(clock or now).minute,
        second=0,
        microsecond=0,
    )


def _parse(value: str | None, reference: datetime | None = None) -> datetime | None:
    """What `strtotime()` would make of it, for the shapes clients send."""
    if not value:
        return None
    reference = reference or datetime.now(ZURICH)
    try:
        return datetime.fromisoformat(value).replace(tzinfo=ZURICH)
    except ValueError:
        pass
    for pattern in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d", "%H:%M:%S", "%H:%M"):
        try:
            parsed = datetime.strptime(value, pattern)
        except ValueError:
            continue
        if pattern.startswith("%H"):
            parsed = parsed.replace(year=reference.year, month=reference.month, day=reference.day)
        return parsed.replace(tzinfo=ZURICH)
    return None
