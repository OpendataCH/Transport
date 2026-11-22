"""The router's own web interface at `/routing/`, passed through to MOTIS.

MOTIS serves a complete single-page application - connections, departures,
isochrones, vehicles on the map - and stays on the internal network. The
page asks for its files, its data (`api/...`) and its map (`tiles/...`)
below `/routing/`; data and map answer at the root of the host as well.

Only what the page needs goes through, named one by one: its files, the
endpoints in ALLOWED_API and the tiles. Numbers stay in BOUNDS, and the
searches share the router's plan slots with the API.
"""

import asyncio
import math
import re
from contextlib import asynccontextmanager
from datetime import datetime, timedelta

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

from .. import errors, settings
from .router import plan_slot

router = APIRouter(include_in_schema=False)

# The router's endpoints the page calls, in full; everything else is 404.
ALLOWED_API = frozenset(
    {
        "v1/geocode",
        "v1/reverse-geocode",
        "v1/health",
        "v1/rentals",
        "v1/map/initial",
        "v1/map/levels",
        "v6/plan",
        "v6/one-to-all",
        "v6/trip",
        "v6/stoptimes",
        "v6/stop",
        "v6/refresh-itinerary",
        "v5/map/trips",  # still asked for by older copies of the page
        "v6/map/trips",
        "v6/map/stops",
        "experimental/map/routes",
    }
)
VEHICLES = frozenset({"v5/map/trips", "v6/map/trips"})
SEARCHES = frozenset({"v6/plan", "v6/one-to-all", "v6/refresh-itinerary"})

# The page's files, as they lie in the router's web folder.
PAGE_FILE = re.compile(
    r"(?:index\.html|favicon\.(?:ico|png)|apple-touch-icon\.png|site\.webmanifest"
    r"|THIRD_PARTY_LICENSES\.md|web-app-manifest-\d+x\d+\.png"
    r"|sprite_sdf(?:@2x)?\.(?:json|png)"
    r"|(?:_app|glyphs|icons|sprites)(?:/(?!\.)[A-Za-z0-9 _.,@-]+)+)?"
)
TILE = re.compile(r"(?:1?[0-9]|2[0-2])/[0-9]{1,7}/[0-9]{1,7}\.mvt")
PARAMETER = re.compile(r"[A-Za-z]+")

# Parameter: lowest, highest. Below, or no number at all, is the router's
# default; above is the highest.
BOUNDS: dict[str, tuple[float, float]] = {
    "numItineraries": (1, 32),
    "maxItineraries": (1, 32),
    "numLegAlternatives": (0, 5),
    "searchWindow": (0, 86400),
    "maxTransfers": (0, 14),
    "maxTravelTime": (1, 2880),
    "minTransferTime": (0, 120),
    "additionalTransferTime": (0, 120),
    "viaMinimumStay": (0, 1440),
    "maxPreTransitTime": (0, 3600),
    "maxPostTransitTime": (0, 3600),
    "maxDirectTime": (0, 21600),
    "maxMatchingDistance": (0, 250),
    "radius": (0, 2000),
    "n": (1, 256),
    "window": (0, 14400),
    "numResults": (1, 50),
    "zoom": (0, 22),
    "precision": (0, 6),
    "passengers": (1, 20),
    "luggage": (1, 20),
}
DECIMAL_BOUNDS: dict[str, tuple[float, float]] = {
    "transferTimeFactor": (1, 10),
    "pedestrianSpeed": (0.3, 5),
    "cyclingSpeed": (0.7, 15),
    "fastestDirectFactor": (0, 100),
    "fastestSlowDirectFactor": (0, 100),
    "placeBias": (0, 100),
}

# Seconds the router may spend on one plan of the page.
PLAN_TIMEOUT = "20"
# The vehicles on the map are those of the next minutes.
MAX_VEHICLES_SPAN = timedelta(hours=1)

# Searches of the page each worker runs at once: fewer than its plan slots,
# so that the API always has some.
PAGE_SEARCHES = 2
_page_plans: asyncio.Semaphore | None = None

# Headers of the router's answer worth passing on. The body is passed on as
# it came, compressed or not, so its encoding goes with it: a map tile is a
# megabyte uncompressed and a tenth of that in gzip.
KEPT_HEADERS = ("content-type", "cache-control", "etag", "last-modified", "content-encoding")


def bounded(query: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """The query as the router gets it: known numbers in range, and once."""
    numbers: dict[str, str | None] = {}
    others = []
    for name, value in query:
        if name in BOUNDS or name in DECIMAL_BOUNDS:
            numbers[name] = _in_range(name, value)
        elif PARAMETER.fullmatch(name):
            others.append((name, value))
    return others + [(name, value) for name, value in numbers.items() if value is not None]


def _in_range(name: str, value: str) -> str | None:
    whole = name in BOUNDS
    low, high = BOUNDS[name] if whole else DECIMAL_BOUNDS[name]
    kept = []
    # viaMinimumStay is one number per via stop.
    for part in value.split(",") if name == "viaMinimumStay" else [value]:
        try:
            number = float(part)
        except ValueError:
            return None
        if math.isnan(number) or number < low:
            return None
        number = min(number, high)
        kept.append(str(int(number) if whole else number))
    return ",".join(kept)


def _check_span(query: list[tuple[str, str]]) -> None:
    given = dict(query)
    try:
        start = datetime.fromisoformat(given["startTime"])
        end = datetime.fromisoformat(given["endTime"])
        fits = timedelta(0) <= end - start <= MAX_VEHICLES_SPAN
    except (KeyError, ValueError, TypeError):
        fits = False
    if not fits:
        raise errors.ApiError(400, "`startTime` to `endTime` must be one hour or less.")


@asynccontextmanager
async def _search_slot():
    """One of the page's few searches, and one of the worker's plan slots."""
    global _page_plans
    if _page_plans is None:
        _page_plans = asyncio.Semaphore(PAGE_SEARCHES)
    slots = _page_plans
    try:
        await asyncio.wait_for(slots.acquire(), timeout=settings.MOTIS_QUEUE_SECONDS)
    except TimeoutError:
        raise errors.ApiError(
            429, "Rate limit error: too many requests at the moment, please try again."
        ) from None
    try:
        async with plan_slot():
            yield
    finally:
        slots.release()


async def _forward(request: Request, path: str, query: list[tuple[str, str]]) -> Response:
    client: httpx.AsyncClient | None = getattr(request.app.state, "motis", None)
    if client is None or not settings.MOTIS_URL:
        return Response("The router is not configured.", status_code=503)
    headers = {"accept-encoding": request.headers.get("accept-encoding", "identity")}
    try:
        async with client.stream("GET", path, params=query, headers=headers) as answer:
            body = b"".join([chunk async for chunk in answer.aiter_raw()])
    except httpx.HTTPError:
        return Response("The router is not reachable.", status_code=503)
    kept = {k: v for k, v in answer.headers.items() if k.lower() in KEPT_HEADERS}
    return Response(body, status_code=answer.status_code, headers=kept)


def _not_found() -> Response:
    return Response("Not found.", status_code=404)


@router.get("/routing")
def routing_slash() -> RedirectResponse:
    # The page's files are relative to it, so it needs the trailing slash.
    return RedirectResponse("/routing/", status_code=301)


@router.get("/routing/{path:path}")
async def routing_page(request: Request, path: str) -> Response:
    if path.startswith("api/"):
        return await routing_api(request, path.removeprefix("api/"))
    if path.startswith("tiles/"):
        return await routing_tiles(request, path.removeprefix("tiles/"))
    if not PAGE_FILE.fullmatch(path):
        return _not_found()
    return await _forward(request, "/" + path, [])


@router.get("/api/{path:path}")
async def routing_api(request: Request, path: str) -> Response:
    if path not in ALLOWED_API:
        return _not_found()
    query = bounded(request.query_params.multi_items())
    if path in VEHICLES:
        _check_span(query)
    if path == "v6/plan":
        query = [pair for pair in query if pair[0] != "timeout"] + [("timeout", PLAN_TIMEOUT)]
    if path in SEARCHES:
        async with _search_slot():
            return await _forward(request, "/api/" + path, query)
    return await _forward(request, "/api/" + path, query)


@router.get("/tiles/{path:path}")
async def routing_tiles(request: Request, path: str) -> Response:
    if not TILE.fullmatch(path):
        return _not_found()
    return await _forward(request, "/tiles/" + path, [])
