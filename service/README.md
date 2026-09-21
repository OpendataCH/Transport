# The Python service (`/v2`)

A FastAPI application that runs **beside** the PHP one, behind the same
hostname. nginx picks between them by path prefix: `/v2/` comes here,
everything else stays with PHP. Nothing about `/v1` changes because this
service exists.

The plan and its stages are in the wiki:
[Plan: a Python service beside the PHP one](https://gitlab.com/opendata.ch/Transport/-/wikis/Plan-v2-FastAPI).
Stages done here: **S0** (the routing, both services alive at once), **S1**
(`/v2/locations`), **S2** (`/v2/stationboard`) and **S3** (`/v2/connections`).
All four routes of `/v1` are answered; its own description is at `/v2/docs`.

## Running it

```sh
cd service
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest
uvicorn transport_api.main:app --reload --port 8000
```

```sh
curl -s localhost:8000/v2/health
{"status":"ok","version":"dev","timezone":"Europe/Zurich","time":"2026-09-21T23:41:02.123456+02:00"}

curl -s 'localhost:8000/v2/locations?query=Bern'
{"stations":[{"id":"8507000","name":"Bern","score":null,
              "coordinate":{"type":"WGS84","x":46.948832,"y":7.439136},
              "distance":null,"icon":"train"}, …]}
```

The tests read the recorded search.ch answers from `test/fixtures/` in the
repository root - the same corpus the PHP suite uses. Nothing in the suite
touches the network.

`tools/diff_v1_v2.py <host>` asks both implementations the same questions on a
running host and compares the answers structurally: order-aware for lists,
order-blind for object keys, `null` kept apart from missing and `int` from
`float`.

```sh
python tools/diff_v1_v2.py https://test-transport-new.opendata.ch
26 of 26 answers identical
```

The board and connection queries ask for a fixed minute two days out,
deliberately.
A board for *now* carries real-time delays that change between the two calls,
and the two requests can land either side of a minute boundary and see
different departures - so two live boards are not comparable at all, not even
`/v1` against itself.

Or through the development compose project at the repository root, which brings
up the PHP application and this one together on port 8000, exactly as the
servers arrange them:

```sh
docker compose up --build
curl -s localhost:8000/v1/locations?query=Bern   # PHP
curl -s localhost:8000/v2/health                 # this
```

## /v2 is /v1, served by something else

Same endpoints, same parameters, same JSON. That is the design, not a stage of
it: two shapes would mean two contracts to maintain forever, and no way to test
the new one against the old. Because the shapes are identical, every answer can
be compared request by request - and once they have been identical on real
traffic for long enough, `/v1` is routed here and the PHP stack is retired.

So the oddities of `/v1` are reproduced on purpose, each one named where it
sits in the code:

- `stations` is the key, although the list carries addresses too;
- a coordinate is `x` (latitude) and `y` (longitude), computed from the Swiss
  grid with the swisstopo approximation - not the WGS84 degrees the upstream
  also sends, which differ by about a metre;
- `score` is always `null` here; it came from HAFAS, which has not been asked
  since the switch to search.ch;
- `icon` is **absent**, not null, when the upstream sends no icon class - the
  "null versus missing" trap, and cheaper to reproduce than to find out which
  client depends on it;
- an empty question answers an empty list, not a 400;
- errors keep the `{"errors": [{"message": …}]}` envelope, and an upstream
  `429` is passed through as a `429`.

What is deliberately *not* the same: `/v2/` reports version `2.0`, and the
machine-readable description is OpenAPI 3.1 at `/v2/openapi.json` rather than
the generated Swagger 2.0 document `/v1` serves. Neither is part of the data a
client reads.

## Three things this service must keep doing

- **Only `/v2`.** Every route lives under that prefix and `tests/test_routing.py`
  asserts that the `/v1` surface returns 404 here. A location block written too
  broadly would otherwise shadow the contract the PHP application owns with a
  half-built answer.
- **Europe/Zurich.** The image installs `tzdata` and sets `TZ`; `/v2/health`
  reports the zone and a timestamp with its offset, so a container that came up
  on UTC says so in the smoke test rather than in the data months later.
- **Forward the caller.** search.ch rate-limits on the IP address and
  User-Agent we name, plus the optional `key`. Lose them and every caller in
  the world shares one bucket and throttles each other, with a rise in 429s as
  the only symptom. `X-Forwarded-For` is read in the application, not by a
  uvicorn flag, so that a test can exercise it.

## The image

Built by `.gitlab-ci.yml` on every push to
`registry.gitlab.com/opendata.ch/transport/service`, tagged with the short
commit SHA and — on the default branch — `latest`. It is a second image beside
the PHP one and deploys and rolls back independently of it.
