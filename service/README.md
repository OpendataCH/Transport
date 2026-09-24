# transport.opendata.ch

The API and the website around it, in one FastAPI application.

| | |
| --- | --- |
| `/v1/locations`, `/v1/stationboard`, `/v1/connections`, `/v1/` | the API |
| `/v1/health` | which build is running, and in which timezone |
| `/v1/docs`, `/v1/documentation`, `/v1/openapi.json` | Swagger UI, ReDoc, OpenAPI 3.1 |
| `/v2/…` | the same routes, undocumented |
| `/`, `/docs.html`, `/examples/`, `/showcase.html`, `/swagger.json` | the website, from `transport_api/site/` |
| `/stats.php` | the statistics page, read from Redis |

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

The tests read the recorded search.ch answers from `test/fixtures/` in the
repository root. Nothing in the suite touches the network.

## /v1 does not change

The API was PHP (Silex) from 2012 to 2026. This service answers exactly as that
implementation did - same endpoints, parameters, JSON, key order and escaping -
because tens of thousands of unattended clients depend on it. Its oddities are
reproduced on purpose and named where they sit in the code, among them:

- `stations` is the key, although the list carries addresses too;
- `x` is latitude and `y` longitude, computed from the Swiss grid;
- `score` is always `null`; `icon` is missing rather than `null`;
- a repeated parameter without brackets keeps its last value (PHP's `parse_str`);
- times with fractions of a second and day-first dates are accepted (`phptime.py`);
- JSON is escaped like `json_encode` (`ü`, `\/`);
- errors keep the `{"errors": [{"message": …}]}` envelope, and an upstream `429`
  is passed through.

`tools/diff_v1_v2.py` and `tools/shadow.py` compare two running
implementations request by request; they were how this one was checked against
the PHP one.

## Things this service must keep doing

- **Europe/Zurich.** The image sets `TZ`; `/v1/health` reports the zone with
  its offset, so a container on UTC shows up in the smoke test.
- **Forward the caller.** search.ch rate-limits on the IP address, User-Agent
  and optional `key` we pass along. `X-Forwarded-For` is trusted from anyone, so
  the container must only be reachable through the proxy in front of it.
- **Count for /stats.php.** With `REDIS_URL` set, every API request is counted
  in the keys the PHP application used (`statistics.py`). The website and the
  statistics page are not counted. A Redis failure never costs an answer.

## The image

Built by `.gitlab-ci.yml` on the default branch into
`registry.gitlab.com/opendata.ch/transport/service`, tagged with the short
commit SHA and `latest`.
