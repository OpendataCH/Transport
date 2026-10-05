# ruff: noqa: E501 - the page is HTML, written as it is served
"""`/licenses.html`: what the service is built from and what it answers from.

The Python packages are read from the running process, so the list is that
of the image actually deployed, every dependency included. The rest - the
data, the services beside the API and what the pages load in the browser -
changes rarely and is listed here by hand.
"""

import html
from functools import cache
from importlib import metadata

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .website import _uncounted

router = APIRouter(include_in_schema=False)

# name, what it is, licence, link
DATA = [
    (
        "Swiss national timetable (GTFS, GTFS-RT, HRDF)",
        "Timetable, real time, operator names",
        "opentransportdata.swiss terms of use (free use, source to be named)",
        "https://opentransportdata.swiss/en/terms-of-use/",
    ),
    (
        "OpenStreetMap, Swiss extract by Geofabrik",
        "Streets for walks, addresses and places",
        "ODbL 1.0 - © OpenStreetMap contributors",
        "https://www.openstreetmap.org/copyright",
    ),
    (
        "sharedmobility.ch (Swiss Federal Office of Energy)",
        "Shared bikes, scooters and cars (GBFS)",
        "Open use, source to be named",
        "https://github.com/SFOE/sharedmobility",
    ),
    (
        "swisstopo national maps",
        "Background of the map example",
        "Free geodata of the Swiss Confederation (OGD), source to be named",
        "https://www.swisstopo.admin.ch/en/terms-of-use-free-geodata-and-geoservices",
    ),
]

SERVICES = [
    (
        "MOTIS",
        "Journey planner behind /connections, map tiles and place search",
        "MIT",
        "https://github.com/motis-project/motis",
    ),
    (
        "PostgreSQL",
        "Timetable database",
        "PostgreSQL License",
        "https://www.postgresql.org/about/licence/",
    ),
    (
        "Redis",
        "Counters of the statistics page",
        "RSALv2 / SSPLv1 / AGPLv3",
        "https://redis.io/legal/licenses/",
    ),
]

BROWSER = [
    (
        "Bootstrap 3.3.6",
        "Layout of the pages",
        "MIT",
        "https://github.com/twbs/bootstrap/blob/v3.3.6/LICENSE",
    ),
    (
        "Leaflet 1.9.4",
        "Map example",
        "BSD-2-Clause",
        "https://github.com/Leaflet/Leaflet/blob/main/LICENSE",
    ),
    (
        "Tabler Icons",
        "Icons of the connection search",
        "MIT",
        "https://github.com/tabler/tabler-icons/blob/main/LICENSE",
    ),
    (
        "Lucide",
        "Tram icon of the connection search",
        "ISC",
        "https://github.com/lucide-icons/lucide/blob/main/LICENSE",
    ),
    (
        "jQuery 1.7.1, jQuery UI 1.8.16",
        "The autocomplete example",
        "MIT",
        "https://jquery.org/license/",
    ),
]


@cache
def python_packages() -> list[tuple[str, str, str, str]]:
    """(name, version, licence, home page) of every installed distribution."""
    found = {}
    for dist in metadata.distributions():
        meta = dist.metadata
        name = meta.get("Name")
        if not name or name.lower() in found:
            continue
        licence = meta.get("License-Expression") or ""
        if not licence:
            classifiers = [
                c.split("::")[-1].strip()
                for c in meta.get_all("Classifier") or []
                if c.startswith("License ::") and "OSI Approved" != c.split("::")[-1].strip()
            ]
            licence = ", ".join(classifiers)
        if not licence:
            text = (meta.get("License") or "").strip()
            licence = text.splitlines()[0][:60] if text else "see project"
        home = meta.get("Home-page") or ""
        if not home:
            for url in meta.get_all("Project-URL") or []:
                label, _, link = url.partition(",")
                if label.strip().lower() in (
                    "homepage",
                    "home",
                    "source",
                    "repository",
                    "documentation",
                ):
                    home = link.strip()
                    break
        found[name.lower()] = (name, dist.version, licence, home)
    return sorted(found.values(), key=lambda row: row[0].lower())


def _rows(rows, columns: int) -> str:
    out = []
    for row in rows:
        *cells, link = row
        first = html.escape(cells[0])
        if link:
            first = f'<a href="{html.escape(link)}" rel="external noopener noreferrer">{first}</a>'
        rest = "".join(f"<td>{html.escape(c)}</td>" for c in cells[1:columns])
        out.append(f"<tr><td>{first}</td>{rest}</tr>")
    return "".join(out)


@router.get("/licenses")
def licenses_short() -> RedirectResponse:
    return RedirectResponse("/licenses.html", status_code=301)


@router.get("/licenses.html")
def licenses(request: Request) -> HTMLResponse:
    packages = python_packages()
    page = f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <title>Licenses - Transport API</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/3.3.6/css/bootstrap.min.css" />
    <link rel="stylesheet" href="media/css/layout.css" />
    <style>
        .lic td {{ font-size: 13px; }}
        .lic td:nth-child(2), .lic td:nth-child(3) {{ white-space: nowrap; }}
        #filter {{ max-width: 22rem; margin-bottom: 8px; }}
    </style>
</head>
<body>
<div class="container">
    <div class="col-sm-10 col-sm-offset-1">
        <header>
            <h1><a href="./">Transport</a></h1>
            <p>Swiss public transport API</p>
        </header>
        <article>
        <h2>Licenses</h2>
        <p>The Transport API is free software under the MIT License, © 2012 Opendata.ch:
            <a href="https://gitlab.com/opendata.ch/Transport">gitlab.com/opendata.ch/Transport</a>.
            What it answers from and what it is built from, with their licences:</p>

        <h3>Data</h3>
        <table class="table table-condensed lic"><thead><tr><th>Source</th><th>Used for</th><th>Terms</th></tr></thead>
        <tbody>{_rows(DATA, 3)}</tbody></table>

        <h3>Services beside the API</h3>
        <table class="table table-condensed lic"><thead><tr><th>Software</th><th>Used for</th><th>License</th></tr></thead>
        <tbody>{_rows(SERVICES, 3)}</tbody></table>

        <h3>In the browser</h3>
        <table class="table table-condensed lic"><thead><tr><th>Library</th><th>Used for</th><th>License</th></tr></thead>
        <tbody>{_rows(BROWSER, 3)}</tbody></table>

        <h3>Python packages <small>{len(packages)}, as installed in the running service</small></h3>
        <input class="form-control input-sm" id="filter" placeholder="Filter packages" aria-label="Filter packages">
        <table class="table table-condensed lic" id="packages"><thead><tr><th>Package</th><th>Version</th><th>License</th></tr></thead>
        <tbody>{_rows([(n, v, lic, home) for n, v, lic, home in packages], 3)}</tbody></table>
        </article>
        <footer class="footer">
            <hr>
            <p>Powered by <a href="https://opendata.ch/">Opendata.ch</a> · <a href="/privacy.html">Privacy policy</a> · <a href="/licenses.html">Licenses</a></p>
        </footer>
    </div>
</div>
<script>
document.getElementById('filter').addEventListener('input', function () {{
    var term = this.value.toLowerCase();
    document.querySelectorAll('#packages tbody tr').forEach(function (row) {{
        row.hidden = term && row.textContent.toLowerCase().indexOf(term) < 0;
    }});
}});
</script>
</body>
</html>"""
    return _uncounted(request, HTMLResponse(page))
