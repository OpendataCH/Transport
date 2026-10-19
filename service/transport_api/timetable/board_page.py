"""The station board example, drawn on the server for a linked station.

`/examples/stationboard.html?station=Bern` comes with the board already in
the page, its own title and description, a canonical address and the
station as structured data, so that a search engine finds a page per stop.
The script in the page takes over from there and refreshes it. Without a
station, or without a timetable, the page is the plain file.

`/sitemap.xml` lists the boards of the busiest stations, and `/robots.txt`
points to it - except on the test host, which asks not to be indexed.
"""

import html
import json
import re
from datetime import datetime
from urllib.parse import urlencode

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, PlainTextResponse, Response

from ..mapping import ZURICH
from ..website import SITE, _uncounted
from . import db
from . import stationboard as board

router = APIRouter(include_in_schema=False)

PAGE = SITE / "examples" / "stationboard.html"
ROWS = 20

# Stations in the sitemap: the busiest, by departures a day.
SITEMAP_STATIONS = 2000
SITEMAP = """
SELECT name FROM gtfs.station WHERE departures > 0
ORDER BY departures DESC LIMIT $1
"""

LONG_DISTANCE = {"IC", "ICE", "ICN", "IR", "IRE", "EC", "EN", "TGV", "RJ", "RJX", "NJ", "PE"}
REGIONAL = {"S", "SN", "R", "RE", "RB", "TER"}


def _is_test(request: Request) -> bool:
    return request.url.hostname is not None and request.url.hostname.startswith("test-")


@router.get("/examples/stationboard.html")
async def station_board_page(request: Request) -> Response:
    wanted = request.query_params.get("station") or request.query_params.get("id")
    pool = getattr(request.app.state, "timetable", None)
    if not wanted or pool is None:
        return _uncounted(request, FileResponse(PAGE, media_type="text/html"))
    try:
        found = await board._station(pool, wanted)
        arrivals = request.query_params.get("type") == "arrival"
        rows = []
        if found is not None:
            when = datetime.now(ZURICH).replace(second=0, microsecond=0)
            calls = await board._calls_at(pool, found["idx"], when, arrivals, None, ROWS)
            here = {"id": found["id"], "name": found["name"], "coordinate": None}
            rows = await board._journeys(pool, calls, here, arrivals)
    except Exception:  # noqa: BLE001 - the plain page is always an answer
        return _uncounted(request, FileResponse(PAGE, media_type="text/html"))
    if found is None:
        return _uncounted(request, FileResponse(PAGE, media_type="text/html"))
    page = PAGE.read_text(encoding="utf-8")
    page = _with_head(page, request, found, arrivals)
    page = page.replace("<!--board-->", _board_html(found["name"], rows, arrivals))
    page = page.replace(
        'id="station" name="station"',
        f'id="station" name="station" value="{html.escape(found["name"])}"',
    )
    if arrivals:
        page = page.replace(
            'class="btn btn-default active" data-type="departure" aria-pressed="true"',
            'class="btn btn-default" data-type="departure" aria-pressed="false"',
        ).replace(
            'class="btn btn-default" data-type="arrival" aria-pressed="false"',
            'class="btn btn-default active" data-type="arrival" aria-pressed="true"',
        )
    response = Response(page, media_type="text/html")
    response.headers["Cache-Control"] = "public, max-age=30"
    return _uncounted(request, response)


def _with_head(page: str, request: Request, station, arrivals: bool) -> str:
    name = station["name"]
    what = "Arrivals at" if arrivals else "Departures from"
    title = f"{what} {name} - Transport"
    description = (
        f"{what} {name}, live: line, destination, platform and real-time delays, "
        "from the open Swiss public transport API."
    )
    query = {"station": name, **({"type": "arrival"} if arrivals else {})}
    canonical = f"{request.base_url}examples/stationboard.html?{urlencode(query)}"
    structured = {
        "@context": "https://schema.org",
        "@type": "Place",
        "name": name,
        "identifier": station["id"],
        "geo": {"@type": "GeoCoordinates", "latitude": station["lat"], "longitude": station["lon"]},
    }
    page = page.replace(
        "<title>Station Board - Transport</title>", f"<title>{html.escape(title)}</title>"
    )
    start = page.index('<meta name="description"')
    end = page.index("/>", start) + 2
    page = (
        page[:start]
        + f'<meta name="description" content="{html.escape(description)}" />'
        + page[end:]
    )
    extra = [
        f'<link rel="canonical" href="{html.escape(canonical)}" />',
        f'<meta property="og:title" content="{html.escape(title)}" />',
        f'<meta property="og:description" content="{html.escape(description)}" />',
        '<script type="application/ld+json">'
        + json.dumps(structured, ensure_ascii=False).replace("</", "<\\/")
        + "</script>",
    ]
    if _is_test(request):
        extra.append('<meta name="robots" content="noindex" />')
    return page.replace("<!--head-->", "\n    ".join(extra))


def _operator(name: str | None) -> str:
    """`BLS-bls` -> `BLS`: the part of the long name people know the operator by."""
    return re.split(r"[-/]", name or "")[0].strip()


def _line(journey: dict) -> str:
    category = journey.get("category") or ""
    number = journey.get("number") or ""
    if not number or number == category:
        return category
    if category in ("B", "BUS"):
        return f"Bus {number}"
    if category == "T":
        return f"Tram {number}"
    return f"{category} {number}" if category in LONG_DISTANCE else f"{category}{number}"


def _board_html(name: str, journeys: list[dict], arrivals: bool) -> str:
    what = "Arrivals at" if arrivals else "Departures from"
    out = [f'<h2 id="board-title" class="h3">{html.escape(what)} {html.escape(name)}</h2>']
    if not journeys:
        return out[0] + '<p class="text-muted">No departures found.</p>'
    out.append(
        '<table class="board"><thead><tr><th>Time</th><th>Line</th><th class="op">Operator</th>'
    )
    # The line's destination either way: /v1 gives it for arrivals too.
    out.append('<th>To</th><th class="pl">Platform</th></tr></thead><tbody>')
    for journey in journeys:
        stop = journey["stop"]
        at = (stop.get("arrival") if arrivals else None) or stop.get("departure") or ""
        delay = stop.get("delay") or 0
        changed = (stop.get("prognosis") or {}).get("platform")
        category = (journey.get("category") or "").upper()
        kind = (
            " long-distance"
            if category in LONG_DISTANCE
            else " regional"
            if category in REGIONAL
            else ""
        )
        late = f' <span class="late">+{delay}</span>' if delay > 0 else ""
        operator = journey.get("operator")
        out.append(
            "<tr>"
            f'<td class="t">{html.escape(at[11:16])}{late}</td>'
            f'<td><span class="badge-product{kind}">{html.escape(_line(journey))}</span></td>'
            f'<td class="op">{html.escape(_operator(operator))}</td>'
            f"<td>{html.escape(journey.get('to') or '')}</td>"
            f'<td class="pl{" changed" if changed else ""}">'
            f"{html.escape(changed or stop.get('platform') or '')}</td>"
            "</tr>"
        )
    out.append("</tbody></table>")
    return "".join(out)


@router.get("/sitemap.xml")
async def sitemap(request: Request) -> Response:
    base = f"{request.base_url}"
    pages = [
        "",
        "docs.html",
        "examples/",
        "examples/connections.html",
        "examples/map.html",
        "showcase.html",
    ]
    urls = [base + page for page in pages]
    pool = getattr(request.app.state, "timetable", None)
    if pool is not None:
        try:
            rows = await db.fetch(pool, SITEMAP, SITEMAP_STATIONS)
        except Exception:  # noqa: BLE001 - the site's own pages are listed anyway
            rows = []
        urls += [
            f"{base}examples/stationboard.html?{urlencode({'station': r['name']})}" for r in rows
        ]
    body = ['<?xml version="1.0" encoding="UTF-8"?>']
    body.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    body += [f"<url><loc>{html.escape(url)}</loc></url>" for url in urls]
    body.append("</urlset>")
    response = Response("\n".join(body), media_type="application/xml")
    response.headers["Cache-Control"] = "public, max-age=86400"
    return _uncounted(request, response)


@router.get("/robots.txt")
async def robots(request: Request) -> Response:
    if _is_test(request):
        text = "User-agent: *\nDisallow: /\n"
    else:
        # The API itself is not for search engines; the website is. An
        # assistant fetching a connection because somebody asked it to is a
        # client of the API, not a crawler — these agents read robots.txt and
        # would otherwise refuse the very calls the API exists for. A group of
        # their own replaces `*` for them.
        text = (
            "User-agent: Claude-User\nUser-agent: ChatGPT-User\nUser-agent: Perplexity-User\n"
            "User-agent: MistralAI-User\nAllow: /\n\n"
            "User-agent: *\nDisallow: /v1/\nDisallow: /v2/\nDisallow: /v1-old/\n"
            "Disallow: /api/\nDisallow: /tiles/\n"
            f"Sitemap: {request.base_url}sitemap.xml\n"
        )
    return _uncounted(request, PlainTextResponse(text))
