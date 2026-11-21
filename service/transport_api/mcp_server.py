"""The API as an MCP server, at /mcp (streamable HTTP).

An assistant (Claude, ChatGPT, Cursor, ...) adds `https://transport.opendata.ch/mcp`
and can then look up stations, connections and departures for the person asking.

* **Stateless, JSON answers.** The service runs several uvicorn workers; a
  session kept in one of them would be lost on the next request landing in
  another. Every request stands on its own, so any worker answers it.
* **The tools call /v1, in process.** Not the handlers: through the whole
  middleware stack, so an answer from the MCP is the same answer, from the same
  30-second cache, in the same error envelope, and counted in /stats like any
  other request - under the caller's address and as the AI client its
  User-Agent names (see `_headers`).
* **Short text, not the /v1 JSON.** A connection in /v1 is several kilobytes of
  coordinates and pass lists; a model reads a few lines per connection better
  and pays less for them.
* **Read only, no login.** Nothing here writes anything, and the tools say so
  (`readOnlyHint`) so a client need not ask before calling them.

The protocol requests themselves (initialize, tools/list) are not counted:
only the /v1 calls a tool makes are API usage.
"""

from contextlib import asynccontextmanager
from datetime import datetime
from typing import Annotated, Any

import httpx
from mcp.server.mcpserver import Context, MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.server.transport_security import TransportSecuritySettings
from mcp.types import Icon, ToolAnnotations
from pydantic import Field
from starlette.responses import HTMLResponse, JSONResponse
from starlette.routing import Route

from . import settings
from .website import SITE as SITE_DIR

SITE = "https://transport.opendata.ch"

#: Part of every User-Agent the tools send to /v1; statistics.AI_CLIENTS names it.
USER_AGENT = f"transport.opendata.ch-mcp/{settings.VERSION}"

READ_ONLY = ToolAnnotations(
    readOnlyHint=True, destructiveHint=False, idempotentHint=True, openWorldHint=True
)

#: The tools answer in short text (see the module docstring); a copy of the same
#: text as structured content would only double every answer.
TOOL = {"annotations": READ_ONLY, "structured_output": False}

mcp = MCPServer(
    name="transport.opendata.ch",
    title="Swiss public transport (transport.opendata.ch)",
    description="Stations, connections and departures of Swiss public transport.",
    website_url=SITE,
    icons=[Icon(src=f"{SITE}/favicon.svg", mime_type="image/svg+xml")],
    version=settings.VERSION,
    instructions=(
        "Swiss public transport timetable with real-time delays, from the national timetable "
        "(opentransportdata.swiss), run by the association Opendata.ch. Times are Swiss local "
        "time (Europe/Zurich). Station names can be given as people say them ('Bern', "
        "'Zürich HB', 'Lausanne, gare'); when a name is ambiguous, call find_stations first "
        "and use the exact name or id it returns. Addresses and places of interest work as "
        "start and destination of a connection too. Coverage is Switzerland (and border "
        "stations); for journeys abroad say that the data ends at the border. The timetable "
        "covers the days from a week ago to about three months ahead; nothing found for a "
        "date outside that range means no data, not no service."
    ),
)

# The app this module is mounted in; set by `install`.
_app = None
# The protocol endpoint of the session manager running now; set by `running`.
_endpoint = None


def install(app) -> None:
    """Add /mcp to the application; `running()` belongs in its lifespan."""
    global _app
    _app = app
    methods = ["GET", "POST", "DELETE"]
    app.router.routes.append(Route("/mcp", endpoint=_Uncounted(), methods=methods))


@asynccontextmanager
async def running():
    """Run a session manager for the life of the application.

    A fresh one each time: the SDK's manager runs once per instance, and an
    application (a test, above all) may start more than once in a process.
    """
    global _endpoint
    starlette_app = mcp.streamable_http_app(
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
        # A public server without login: the Host and Origin checks protect a
        # server on localhost from web pages, which is not this one.
        transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
    )
    route = next(r for r in starlette_app.routes if isinstance(r, Route) and r.path == "/mcp")
    async with mcp.session_manager.run():
        _endpoint = route.app
        try:
            yield
        finally:
            _endpoint = None


class _Uncounted:
    """The /mcp endpoint, as a plain ASGI app (a class, so Starlette passes it scope,
    receive and send rather than a request).

    The protocol requests are not API usage; the /v1 calls of a tool are.
    """

    async def __call__(self, scope, receive, send):
        scope.setdefault("state", {})["stats_skip"] = True
        if _is_browser(scope):
            await _BROWSER_PAGE(scope, receive, send)
            return
        if _endpoint is None:
            response = JSONResponse({"error": "MCP server not running"}, status_code=503)
            await response(scope, receive, send)
            return
        await _endpoint(scope, receive, send)


# What someone who opens /mcp in a browser sees: what the address is for and
# how to add it. A page of the website, read once at import.
_BROWSER_PAGE = HTMLResponse((SITE_DIR / "mcp.html").read_text(encoding="utf-8"))


def _is_browser(scope) -> bool:
    """A GET that wants a page, not an event stream: someone opened the URL."""
    if scope.get("method") != "GET":
        return False
    accept = dict(scope.get("headers") or []).get(b"accept", b"").decode("latin-1")
    return "text/html" in accept and "text/event-stream" not in accept


# --- Calling /v1 ----------------------------------------------------------------


def _headers(ctx: Context | None) -> dict[str, str]:
    """The caller's address and client, passed on so /stats tells callers apart."""
    headers = {"user-agent": USER_AGENT, "accept": "application/json"}
    request = getattr(getattr(ctx, "request_context", None), "request", None) if ctx else None
    if request is not None:
        client = request.client.host if request.client else None
        if client:
            headers["x-forwarded-for"] = client
        caller = request.headers.get("user-agent")
        if caller:
            headers["user-agent"] = f"{USER_AGENT} ({caller[:200]})"
    return headers


async def _get(path: str, params: list[tuple[str, str]], ctx: Context | None) -> dict[str, Any]:
    transport = httpx.ASGITransport(app=_app)
    async with httpx.AsyncClient(
        transport=transport, base_url="http://transport.internal", timeout=60
    ) as client:
        response = await client.get(path, params=params, headers=_headers(ctx))
    try:
        body = response.json()
    except ValueError:
        body = {}
    if response.status_code >= 400 or "errors" in body:
        messages = [e.get("message", "") for e in body.get("errors", []) if isinstance(e, dict)]
        raise ToolFailure("; ".join(m for m in messages if m) or f"HTTP {response.status_code}")
    return body


class ToolFailure(ToolError):
    """An answer of /v1 that is an error; the model gets its message, flagged as an error."""


# --- Formatting -----------------------------------------------------------------


def _clock(value: str | None) -> str:
    if not value:
        return "?"
    return datetime.fromisoformat(value).strftime("%H:%M")


def _day(value: str | None) -> str:
    if not value:
        return ""
    return datetime.fromisoformat(value).strftime("%a %Y-%m-%d")


def _minutes(duration: str | None) -> str:
    """'00d01:23:00' as '1 h 23 min'."""
    if not duration:
        return "?"
    days, _, rest = duration.partition("d")
    hours, minutes, _ = (int(p) for p in rest.split(":"))
    hours += int(days) * 24
    return f"{hours} h {minutes:02d} min" if hours else f"{minutes} min"


def _stop(stop: dict, time_key: str) -> str:
    """'16:31 Bern, platform 8, +4 min'."""
    name = (stop.get("station") or stop.get("location") or {}).get("name") or "?"
    parts = [f"{_clock(stop.get(time_key))} {name}"]
    platform = (stop.get("prognosis") or {}).get("platform") or stop.get("platform")
    if platform:
        parts.append(f"platform {platform}")
    if stop.get("delay"):
        parts.append(f"+{stop['delay']} min")
    return ", ".join(parts)


def _line(journey: dict) -> str:
    """'IC 1 to St. Gallen (SBB)'."""
    category = journey.get("category") or ""
    # The line ('1' of IC 1), or for a train without one its number, zero-padded
    # ('000377' of an ICE); '?' when the timetable has neither.
    number = (journey.get("number") or "").lstrip("0")
    if number == "?":
        number = ""
    label = f"{category} {number}".strip() or journey.get("name") or "?"
    if journey.get("to"):
        label += f" to {journey['to']}"
    if journey.get("operator"):
        label += f" ({journey['operator']})"
    return label


def _connection(index: int, c: dict) -> str:
    start, end = c["from"], c["to"]
    transfers = c.get("transfers") or 0
    head = (
        f"{index}. {_day(start.get('departure'))} {_stop(start, 'departure')} → "
        f"{_stop(end, 'arrival')} · {_minutes(c.get('duration'))} · "
        + ("direct" if transfers == 0 else f"{transfers} change" + ("s" if transfers > 1 else ""))
    )
    lines = [head]
    for section in c.get("sections") or []:
        if section.get("journey"):
            lines.append(
                f"   - {_line(section['journey'])}: {_stop(section['departure'], 'departure')}"
                f" → {_stop(section['arrival'], 'arrival')}"
            )
        elif section.get("walk") is not None:
            walk = section["walk"].get("duration")
            to = (section.get("arrival") or {}).get("station") or {}
            minutes = f"{round(int(walk) / 60)} min " if walk else ""
            lines.append(f"   - walk {minutes}to {to.get('name') or '?'}")
    return "\n".join(lines)


# --- Tools ----------------------------------------------------------------------


@mcp.tool(title="Find stations", **TOOL)
async def find_stations(
    query: Annotated[
        str, Field(description="Name or part of a name, e.g. 'Bern' or 'Basel, Bank'.")
    ],
    ctx: Context,
) -> str:
    """Find stations and stops by name. Returns their exact names and ids, best match first."""
    body = await _get("/v1/locations", [("query", query), ("type", "station")], ctx)
    stations = body.get("stations") or []
    if not stations:
        return f"No station found for '{query}'."
    return "\n".join(
        f"- {s.get('name')} (id {s.get('id')}{', ' + s['icon'] if s.get('icon') else ''})"
        for s in stations[:15]
    )


@mcp.tool(title="Stops nearby", **TOOL)
async def stations_nearby(
    latitude: Annotated[float, Field(description="WGS84 latitude, e.g. 46.9488.")],
    longitude: Annotated[float, Field(description="WGS84 longitude, e.g. 7.4391.")],
    ctx: Context,
) -> str:
    """The stops closest to a point, with their distance in metres."""
    body = await _get("/v1/locations", [("x", str(latitude)), ("y", str(longitude))], ctx)
    stations = [s for s in body.get("stations") or [] if s.get("id")]
    if not stations:
        return "No stop found near that point."
    return "\n".join(
        f"- {s.get('name')} (id {s.get('id')}), {s.get('distance')} m" for s in stations[:10]
    )


@mcp.tool(title="Connections", **TOOL)
async def connections(
    origin: Annotated[str, Field(description="Start: station name or id, address or place.")],
    destination: Annotated[str, Field(description="Destination, like origin.")],
    ctx: Context,
    date: Annotated[str | None, Field(description="YYYY-MM-DD; today if left out.")] = None,
    time: Annotated[
        str | None, Field(description="hh:mm, Swiss local time; now if left out.")
    ] = None,
    arrive_by: Annotated[
        bool, Field(description="True if `time` is the latest arrival rather than departure.")
    ] = False,
    via: Annotated[
        list[str] | None, Field(description="Up to two stations the journey must pass.")
    ] = None,
    limit: Annotated[int, Field(ge=1, le=8, description="Number of connections.")] = 4,
) -> str:
    """Public transport connections from A to B: times, platforms, delays, changes, lines."""
    params = [("from", origin), ("to", destination), ("limit", str(limit))]
    if date:
        params.append(("date", date))
    if time:
        params.append(("time", time))
    if arrive_by:
        params.append(("isArrivalTime", "1"))
    params.extend(("via[]", v) for v in (via or [])[:2])
    body = await _get("/v1/connections", params, ctx)
    found = body.get("connections") or []
    if not found:
        return f"No connection found from '{origin}' to '{destination}'."
    start = (body.get("from") or {}).get("name") or origin
    end = (body.get("to") or {}).get("name") or destination
    lines = [f"Connections {start} → {end} (times Swiss local, delays as +min):"]
    lines += [_connection(i, c) for i, c in enumerate(found, 1)]
    return "\n".join(lines)


@mcp.tool(title="Departures", **TOOL)
async def departures(
    station: Annotated[str, Field(description="Station name or id.")],
    ctx: Context,
    when: Annotated[
        str | None, Field(description="'YYYY-MM-DD hh:mm', Swiss local time; now if left out.")
    ] = None,
    limit: Annotated[int, Field(ge=1, le=40, description="Number of entries.")] = 10,
    arrivals: Annotated[
        bool, Field(description="True for arrivals instead of departures.")
    ] = False,
) -> str:
    """The departure (or arrival) board of a station, with platforms and delays."""
    params = [("station", station), ("limit", str(limit))]
    if when:
        params.append(("datetime", when))
    if arrivals:
        params.append(("type", "arrival"))
    body = await _get("/v1/stationboard", params, ctx)
    board = body.get("stationboard") or []
    name = (body.get("station") or {}).get("name") or station
    if not board:
        return f"No {'arrivals' if arrivals else 'departures'} found for '{name}'."
    key = "arrival" if arrivals else "departure"
    first = ((board[0].get("stop") or {}).get(key)) if board else None
    lines = [f"{'Arrivals at' if arrivals else 'Departures from'} {name}, {_day(first)}:"]
    for entry in board:
        stop = entry.get("stop") or {}
        when_ = stop.get(key)
        platform = (stop.get("prognosis") or {}).get("platform") or stop.get("platform")
        extra = []
        if platform:
            extra.append(f"platform {platform}")
        if stop.get("delay"):
            extra.append(f"+{stop['delay']} min")
        lines.append(
            f"- {_clock(when_)} {_line(entry)}" + (f" · {', '.join(extra)}" if extra else "")
        )
    return "\n".join(lines)
