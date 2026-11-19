# transport.opendata.ch

The API and the website around it, in one FastAPI application.

| | |
| --- | --- |
| `/v1/locations`, `/v1/stationboard`, `/v1/connections`, `/v1/` | the API |
| `/v1/health` | which build is running, and in which timezone |
| `/v1/docs`, `/v1/documentation`, `/v1/openapi.json` | Swagger UI, ReDoc, OpenAPI 3.1 |
| `/v2/…` | the same routes, undocumented |
| `/`, `/docs.html`, `/examples/`, `/showcase.html`, `/swagger.json` | the website, from `transport_api/site/` |
| `/stats` (and the old `/stats.php`) | the statistics page, read from Redis |
| `POST /ojp20` | Open Journey Planner 2.0, answered by the router (`timetable/ojp.py`) |

Documentation for operators is in the
[wiki](https://gitlab.com/opendata.ch/Transport/-/wikis/home).

## Running it

```sh
cd service
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest
uvicorn transport_api.main:app --reload --port 8000
```

Or with Redis, from the repository root: `docker compose up --build`, then
`http://localhost:8000/`.

The timetable tests need a Postgres in `TEST_DATABASE_URL` (CI has one) and
are skipped without it; the router is replaced by recorded answers. Nothing in
the suite touches the network.

## /v1 does not change

The API was PHP (Silex) from 2012 to 2026. This service answers exactly as that
implementation did - same endpoints, parameters, JSON, key order and escaping -
because tens of thousands of unattended clients depend on it. Its oddities are
reproduced on purpose and named where they sit in the code, among them:

- `stations` is the key, although the list carries addresses too;
- `x` is latitude and `y` longitude;
- `score` is always `null`; `icon` is missing rather than `null`;
- a repeated parameter without brackets keeps its last value (PHP's `parse_str`);
- times with fractions of a second and day-first dates are accepted (`phptime.py`);
- JSON is escaped like `json_encode` (`ü`, `\/`);
- errors keep the `{"errors": [{"message": …}]}` envelope; a busy router is a
  `429`.

`tools/shadow.py` and `tools/compare_random.py` compare two running hosts
request by request; they were how this one was checked against the PHP one and
against search.ch.

## /ojp20

OJP 2.0, the XML interface of the national journey planner on
opentransportdata.swiss, at the same path. MOTIS answers it itself; the route
in front translates stop ids (SLOID `ch:1:sloid:7000` or DiDok `8507000` in,
SLOID out, instead of the router's `ch_Parentch:1:sloid:7000`), rewrites the
namespace prefixes the router insists on, and repairs its answers until they
validate against the OJP 2.0 schema. Each service gets its public code,
product category and train number from the timetable, as the national
planner gives them. Trip, stop event, trip info and location
requests pass; fares, refinement and the rest do not. Location requests by
name or stop id need `MOTIS_GEOCODING=1`, i.e. a router built with
`MOTIS_TILES`: without its place search, MOTIS 2.11.4 crashes on a lookup by
id.

## Things this service must keep doing

- **Europe/Zurich.** The image sets `TZ`; `/v1/health` reports the zone with
  its offset, so a container on UTC shows up in the smoke test.
- **Know the caller.** The statistics tell clients apart by their address.
  `X-Forwarded-For` is trusted from anyone, so the container must only be
  reachable through the proxy in front of it.
- **Count for /stats.php.** With `REDIS_URL` set, every API request is counted
  in the keys the PHP application used (`statistics.py`). The website and the
  statistics page are not counted. A Redis failure never costs an answer.

## Checks

- `pytest` in CI, with a JUnit report and coverage (at least 94 %) shown in
  GitLab.
- `tools/smoke.py <base URL>` asks a running instance what breaks silently:
  build and timezone, website, statistics page, error envelope, one question to
  the timetable. CI runs it against the image it just built (`smoke:image`), and
  offers it as buttons against staging and production after a deploy
  (`smoke:staging`, `smoke:production`).

## The image

Built by `.gitlab-ci.yml` on the default branch into
`registry.gitlab.com/opendata.ch/transport/service`, tagged with the short
commit SHA and `latest`.
