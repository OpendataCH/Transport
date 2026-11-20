# ruff: noqa: E501 - the page is HTML, written as it is served
"""`/licenses.html`: what the service is built from and what it answers from.

The Python packages are read from the running process, so the list is that
of the image actually deployed, every dependency included. The rest - the
data, the services beside the API and what the pages load in the browser -
changes rarely and is listed here by hand.
"""

import html
import re
from datetime import datetime
from functools import cache
from importlib import metadata

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from .statistics import ZONE
from .website import _uncounted

router = APIRouter(include_in_schema=False)

# name, what it is, licence, project link, licence link
DATA = [
    (
        "Swiss national timetable (GTFS, GTFS-RT, HRDF)",
        "Timetable, real time, operator names",
        "opentransportdata.swiss terms of use",
        "https://opentransportdata.swiss/",
        "https://opentransportdata.swiss/en/terms-of-use/",
    ),
    (
        "Occupancy forecast of the railways (SBB, BLS, SOB, Thurbo, zb)",
        "capacity1st/capacity2nd, occupancy in /ojp20",
        "opentransportdata.swiss terms of use",
        "https://data.opentransportdata.swiss/en/dataset/occupancy-forecast-json-dataset",
        "https://opentransportdata.swiss/en/terms-of-use/",
    ),
    (
        "National fare service NOVA (OJPFare, beta)",
        "Ticket prices of /fare",
        "opentransportdata.swiss terms of use",
        "https://opendata.swiss/en/perma/ojpfare@oevch",
        "https://opentransportdata.swiss/en/terms-of-use/",
    ),
    (
        "OpenStreetMap, Swiss extract by Geofabrik",
        "Streets for walks, addresses and places",
        "ODbL 1.0, © OpenStreetMap contributors",
        "https://download.geofabrik.de/europe/switzerland.html",
        "https://www.openstreetmap.org/copyright",
    ),
    (
        "sharedmobility.ch (Swiss Federal Office of Energy)",
        "Shared bikes, scooters and cars (GBFS)",
        "Open use, must provide the source (BY)",
        "https://opendata.swiss/en/dataset/standorte-und-verfugbarkeit-von-shared-mobility-angeboten",
        "https://opendata.swiss/en/terms-of-use#terms_by",
    ),
    (
        "swisstopo national maps",
        "Background of the map example",
        "Free geodata of the Swiss Confederation (OGD)",
        "https://www.swisstopo.admin.ch/",
        "https://www.swisstopo.admin.ch/en/terms-of-use-free-geodata-and-geoservices",
    ),
]

SERVICES = [
    (
        "MOTIS",
        "Journey planner behind /connections, map tiles and place search",
        "MIT",
        "https://github.com/motis-project/motis",
        "https://github.com/motis-project/motis/blob/master/LICENSE",
    ),
    (
        "PostgreSQL",
        "Timetable database",
        "PostgreSQL License",
        "https://www.postgresql.org/",
        "https://www.postgresql.org/about/licence/",
    ),
    (
        "Redis",
        "Counters of the statistics page",
        "RSALv2 / SSPLv1 / AGPLv3",
        "https://redis.io/",
        "https://redis.io/legal/licenses/",
    ),
]

BROWSER = [
    (
        "Bootstrap 3.4.1",
        "Layout of the pages",
        "MIT",
        "https://getbootstrap.com/docs/3.4/",
        "https://github.com/twbs/bootstrap/blob/v3.4.1/LICENSE",
    ),
    (
        "Leaflet 1.9.4",
        "Map example",
        "BSD-2-Clause",
        "https://leafletjs.com/",
        "https://github.com/Leaflet/Leaflet/blob/main/LICENSE",
    ),
    (
        "Tabler Icons",
        "Icons of the connection search",
        "MIT",
        "https://tabler.io/icons",
        "https://github.com/tabler/tabler-icons/blob/main/LICENSE",
    ),
    (
        "Lucide",
        "Tram icon of the connection search",
        "ISC",
        "https://lucide.dev/",
        "https://github.com/lucide-icons/lucide/blob/main/LICENSE",
    ),
    (
        "jQuery 3.7.1",
        "Statistics page",
        "MIT",
        "https://jquery.com/",
        "https://jquery.org/license/",
    ),
    (
        "Chart.js 4.5.1, chartjs-plugin-zoom 2.2.0, chartjs-adapter-moment 1.0.1",
        "Charts of the statistics page",
        "MIT",
        "https://www.chartjs.org/",
        "https://github.com/chartjs/Chart.js/blob/v4.5.1/LICENSE.md",
    ),
    (
        "Moment.js 2.30.1, Hammer.js 2.0.8",
        "Time axis and zoom of the statistics page",
        "MIT",
        "https://momentjs.com/",
        "https://github.com/moment/moment/blob/2.30.1/LICENSE",
    ),
]

# Licence names in package metadata, as SPDX identifiers.
SPDX = {
    "MIT License": "MIT",
    "Apache Software License": "Apache-2.0",
    "Python Software Foundation License": "PSF-2.0",
    "ISC License (ISCL)": "ISC",
    "Mozilla Public License 2.0 (MPL 2.0)": "MPL-2.0",
}
SPDX_ID = re.compile(r"^[A-Za-z0-9.\-+]+$")


def licence_link(licence: str, package: str) -> str:
    """The licence's text at spdx.org when it is one SPDX identifier, else the package on PyPI."""
    single = SPDX.get(licence, licence)
    if SPDX_ID.match(single) and not single.lower().startswith("see"):
        return f"https://spdx.org/licenses/{single}.html"
    return f"https://pypi.org/project/{package}/"


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
        found[name.lower()] = (
            name,
            dist.version,
            licence,
            home or f"https://pypi.org/project/{name}/",
            licence_link(licence, name),
        )
    return sorted(found.values(), key=lambda row: row[0].lower())


def _link(text: str, href: str) -> str:
    text = html.escape(text)
    if not href:
        return text
    return f'<a href="{html.escape(href)}" rel="external noopener noreferrer">{text}</a>'


def _rows(rows) -> str:
    """name (to its project), what it is or its version, licence (to its text)."""
    return "".join(
        f"<tr><td>{_link(name, project)}</td><td>{html.escape(middle)}</td>"
        f"<td>{_link(licence, licence_href)}</td></tr>"
        for name, middle, licence, project, licence_href in rows
    )


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
    <link rel="icon" href="/favicon.ico" sizes="any" />
    <link rel="icon" href="/favicon.svg" type="image/svg+xml" />
    <link rel="apple-touch-icon" href="/apple-touch-icon.png" />
    <link rel="manifest" href="/site.webmanifest" />
    <meta name="theme-color" content="#E61414" />
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/twitter-bootstrap/3.4.1/css/bootstrap.min.css" />
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
            <h1><a href="./"><img class="logo" src="/media/images/logo.svg" alt="" />Transport</a></h1>
            <p>Swiss public transport API</p>
        </header>
        <article>
        <h2>Licenses</h2>
        <p>The Transport API is free software under the MIT License, © 2012–{datetime.now(ZONE).year} Opendata.ch:
            <a href="https://gitlab.com/opendata.ch/Transport">gitlab.com/opendata.ch/Transport</a>.</p>

        <h3>Data</h3>
        <table class="table table-condensed lic"><thead><tr><th>Source</th><th>Used for</th><th>Terms</th></tr></thead>
        <tbody>{_rows(DATA)}</tbody></table>

        <h3>Services beside the API</h3>
        <table class="table table-condensed lic"><thead><tr><th>Software</th><th>Used for</th><th>License</th></tr></thead>
        <tbody>{_rows(SERVICES)}</tbody></table>

        <h3>In the browser</h3>
        <table class="table table-condensed lic"><thead><tr><th>Library</th><th>Used for</th><th>License</th></tr></thead>
        <tbody>{_rows(BROWSER)}</tbody></table>

        <h3>Python packages <small>{len(packages)}, as installed in the running service</small></h3>
        <input class="form-control input-sm" id="filter" placeholder="Filter packages" aria-label="Filter packages">
        <table class="table table-condensed lic" id="packages"><thead><tr><th>Package</th><th>Version</th><th>License</th></tr></thead>
        <tbody>{_rows(packages)}</tbody></table>
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
