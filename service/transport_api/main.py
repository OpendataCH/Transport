"""The FastAPI application.

It answers **`/v1`**, the contract tens of thousands of unattended clients
speak, written to be indistinguishable from the PHP application it replaced,
and **`/v2`**: the same parameters and the same JSON, but locations and station
boards read from our own copy of the national timetable (`timetable/`)
instead of search.ch, and connections come from our own router (MOTIS) when
MOTIS_URL is set - otherwise from search.ch.

Stage S6 is what made `/v1` the documented prefix here. Until then this service
refused the whole `/v1` surface on purpose, so that a routing mistake could not
shadow the old contract with a half-built answer. That guard has done its work
and is retired; the PHP application now serves only the website around the
API.

The machine-readable description covers `/v1`. `/v2` is an experiment and is
kept out of the document until it has been compared long enough.

With V1_FROM_TIMETABLE on, the timetable answers `/v1` as well, and the
search.ch translation moves to `/v1-old`.
"""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

import httpx
from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.docs import get_redoc_html, get_swagger_ui_html
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from . import (
    compat,
    connections,
    errors,
    licenses_page,
    locations,
    response_cache,
    settings,
    stationboard,
    statistics,
    stats_page,
    upstream,
)
from .models import ApiInfo
from .timetable import board_page, routing_ui
from .timetable import connections as timetable_connections
from .timetable import db as timetable_db
from .timetable import locations as timetable_locations
from .timetable import map as timetable_map
from .timetable import stationboard as timetable_stationboard

# The prefix a client should use, and the one it may. Both answer the same
# thing; only the first is described.
PREFIX = "/v1"
ALIAS = "/v2"
# The search.ch translation, once /v1 answers from the timetable.
OLD = "/v1-old"

# What `/v1/` and `/v2/` report about themselves. /v1 says 1.0 because that is
# what it has always said and the answer is compared byte for byte.
API_VERSIONS = {PREFIX: "1.0", ALIAS: "2.0", OLD: "1.0"}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """One connection pool for the life of the process, not one per request."""
    app.state.http = upstream.build_client()
    app.state.timetable = await timetable_db.connect()
    app.state.motis = (
        httpx.AsyncClient(base_url=settings.MOTIS_URL, timeout=settings.UPSTREAM_TIMEOUT)
        if settings.MOTIS_URL
        else None
    )
    redis = statistics.connect()
    app.state.statistics = statistics.Statistics(redis) if redis is not None else None
    try:
        yield
    finally:
        await app.state.http.aclose()
        if app.state.timetable is not None:
            await app.state.timetable.close()
        if app.state.motis is not None:
            await app.state.motis.aclose()
        if redis is not None:
            await redis.aclose()


app = FastAPI(
    title="transport.opendata.ch",
    version=settings.VERSION,
    summary="The Swiss public transport API",
    description=(
        "Timetable data for Swiss public transport, from the national timetable "
        "and its real-time feed on [opentransportdata.swiss](https://opentransportdata.swiss/). "
        "The answers of search.ch, which this API translated before, stay at `/v1-old`."
        if settings.V1_FROM_TIMETABLE
        else "Timetable data for Swiss public transport, from "
        "[search.ch](https://timetable.search.ch/). This service translates; "
        "it stores nothing."
    ),
    lifespan=lifespan,
    # Under the prefix, so that the nginx location block is the only thing that
    # has to know about it. The Swagger 2.0 document the PHP application
    # generated stays where it was, at /swagger.json, as a file of the website;
    # this is a different document in a different dialect and the two never
    # meet.
    openapi_url=f"{PREFIX}/openapi.json",
    docs_url=f"{PREFIX}/docs",
    redoc_url=f"{PREFIX}/documentation",
)

# The 30-second memory of repeated answers, innermost: what it answers is
# still counted by the statistics around it.
app.add_middleware(
    response_cache.ResponseCacheMiddleware,
    redis_of=lambda: getattr(getattr(app.state, "statistics", None), "redis", None),
)

# Counting for /stats.php. Added before the proxy-headers middleware so that it
# runs inside it: Starlette wraps the last one added outermost, and only inside
# is the client address the caller's rather than nginx's.
app.add_middleware(
    statistics.StatisticsMiddleware,
    statistics_of=lambda: getattr(app.state, "statistics", None),
)

# X-Forwarded-For becomes the request's client address. This is the single
# most consequential line in the service: search.ch rate-limits on the caller
# we name, so without it every caller in the world shares one bucket and
# throttles each other - and the only symptom is a rise in 429s. It is done
# here rather than by a uvicorn flag so that a test can exercise it.
# Trusting every proxy is safe because the container is never reached except
# through the nginx in front of it.
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts="*")

# Browsers call this API directly, as they always have.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

errors.install(app)
compat.install(app)

# Outermost, so that its headers reach every answer, CORS preflights and the
# errors of the middlewares inside included.
app.add_middleware(compat.PhpCompatMiddleware)


class Health(BaseModel):
    """What the service says about itself."""

    status: Literal["ok"] = "ok"
    version: str = Field(description="Short commit SHA of the image, or 'dev'.")
    timezone: str = Field(description="The zone all local times are expressed in.")
    time: datetime = Field(description="Now, in that zone, with its offset.")


def health() -> Health:
    """Who is running, and in which timezone.

    The timestamp is not decoration: it carries the offset, so a container that
    came up on UTC says so in the smoke test instead of in the data months
    later.
    """
    return Health(
        version=settings.VERSION,
        timezone=settings.TIMEZONE,
        time=datetime.now(ZoneInfo(settings.TIMEZONE)),
    )


def info_of(api_version: str):
    """The `/v1/` answer, which names the API rather than the build."""

    def info() -> ApiInfo:
        return ApiInfo(
            date=datetime.now(ZoneInfo(settings.TIMEZONE)).isoformat(timespec="seconds"),
            author="Opendata.ch",
            version=api_version,
        )

    return info


def from_search_ch(prefix: str) -> bool:
    """Whether a prefix is answered by the search.ch translation."""
    return prefix == OLD or (prefix == PREFIX and not settings.V1_FROM_TIMETABLE)


for prefix, api_version in API_VERSIONS.items():
    router = APIRouter(prefix=prefix)
    router.add_api_route("/", info_of(api_version), summary="What this API is")
    router.add_api_route("/health", health, summary="Liveness and identity of the service")
    if from_search_ch(prefix):
        router.include_router(locations.router, tags=["locations"])
        router.include_router(stationboard.router, tags=["stationboard"])
        router.include_router(connections.router, tags=["connections"])
    else:
        router.include_router(timetable_locations.router, tags=["locations"])
        router.include_router(timetable_stationboard.router, tags=["stationboard"])
        router.include_router(
            timetable_connections.router if settings.MOTIS_URL else connections.router,
            tags=["connections"],
        )
    app.include_router(router, include_in_schema=prefix == PREFIX)


# What the map example draws: shaped for a map, not part of the /v1 contract.
app.include_router(timetable_map.router, prefix=ALIAS, include_in_schema=False)
# The router's own web interface, at /routing/.
app.include_router(routing_ui.router)
# The station board example drawn on the server, the sitemap and robots.txt.
app.include_router(board_page.router)

app.include_router(stats_page.router)
app.include_router(licenses_page.router)


# The alias gets the same three documents, at its own addresses, so that a
# bookmark from before the flip still opens something.
@app.get(f"{ALIAS}/openapi.json", include_in_schema=False)
def alias_openapi() -> JSONResponse:
    return JSONResponse(app.openapi())


@app.get(f"{ALIAS}/docs", include_in_schema=False)
def alias_docs() -> HTMLResponse:
    return get_swagger_ui_html(openapi_url=f"{PREFIX}/openapi.json", title="transport.opendata.ch")


@app.get(f"{ALIAS}/documentation", include_in_schema=False)
def alias_redoc() -> HTMLResponse:
    return get_redoc_html(openapi_url=f"{PREFIX}/openapi.json", title="transport.opendata.ch")
