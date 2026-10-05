"""The router's own web interface at `/routing/`, passed through to MOTIS.

MOTIS serves a complete single-page application - connections, departures,
isochrones, vehicles on the map - and stays on the internal network. The
page loads its files relative to where it is (so `/routing/` works) but asks
for its data at `/api/...` and its map at `/tiles/...` from the root of the
host; neither is used by this service, so both are passed on as well.

Only what the page needs goes through: the router's debugging endpoints and
anything else stay internal.
"""

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, Response

from .. import settings

router = APIRouter(include_in_schema=False)

# The router's endpoints the page calls. A prefix match; everything else is 404.
ALLOWED_API = (
    "v1/geocode",
    "v1/reverse-geocode",
    "v1/map/",
    "v1/rentals",
    "v1/health",
    "v6/plan",
    "v6/one-to-all",
    "v6/one-to-many",
    "v6/trip",
    "v6/stoptimes",
    "v6/stop",
    "v6/map/",
    "v6/refresh-itinerary",
    "experimental/map/",
)

# Headers of the router's answer worth passing on. The body is passed on as
# it came, compressed or not, so its encoding goes with it: a map tile is a
# megabyte uncompressed and a tenth of that in gzip.
KEPT_HEADERS = ("content-type", "cache-control", "etag", "last-modified", "content-encoding")


async def _forward(request: Request, path: str) -> Response:
    client: httpx.AsyncClient | None = getattr(request.app.state, "motis", None)
    if client is None or not settings.MOTIS_URL:
        return Response("The router is not configured.", status_code=503)
    headers = {"accept-encoding": request.headers.get("accept-encoding", "identity")}
    try:
        query = request.query_params
        async with client.stream("GET", path, params=query, headers=headers) as answer:
            body = b"".join([chunk async for chunk in answer.aiter_raw()])
    except httpx.HTTPError:
        return Response("The router is not reachable.", status_code=503)
    kept = {k: v for k, v in answer.headers.items() if k.lower() in KEPT_HEADERS}
    return Response(body, status_code=answer.status_code, headers=kept)


@router.get("/routing")
def routing_slash() -> RedirectResponse:
    # The page's files are relative to it, so it needs the trailing slash.
    return RedirectResponse("/routing/", status_code=301)


@router.get("/routing/{path:path}")
async def routing_page(request: Request, path: str) -> Response:
    return await _forward(request, "/" + path)


@router.get("/api/{path:path}")
async def routing_api(request: Request, path: str) -> Response:
    if not path.startswith(ALLOWED_API):
        return Response("Not found.", status_code=404)
    return await _forward(request, "/api/" + path)


@router.get("/tiles/{path:path}")
async def routing_tiles(request: Request, path: str) -> Response:
    return await _forward(request, "/tiles/" + path)
