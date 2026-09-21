# The Python service (`/v2`)

A FastAPI application that runs **beside** the PHP one, behind the same
hostname. nginx picks between them by path prefix: `/v2/` comes here,
everything else stays with PHP. Nothing about `/v1` changes because this
service exists.

The plan and its stages are in the wiki:
[Plan: a Python service beside the PHP one](https://gitlab.com/opendata.ch/Transport/-/wikis/Plan-v2-FastAPI).
Stages done here: **S0** (the routing, both services alive at once) and **S1**
(`/v2/locations`). It answers `/v2/health` and `/v2/locations`; its own
description is at `/v2/docs`.

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
{"locations":[{"type":"station","id":"8507000","name":"Bern",
               "coordinate":{"lat":46.948823,"lon":7.439123},
               "distance":null,"category":"train"}, …]}
```

The tests read the recorded search.ch answers from `test/fixtures/` in the
repository root - the same corpus the PHP suite uses. Nothing in the suite
touches the network.

Or through the development compose project at the repository root, which brings
up the PHP application and this one together on port 8000, exactly as the
servers arrange them:

```sh
docker compose up --build
curl -s localhost:8000/v1/locations?query=Bern   # PHP
curl -s localhost:8000/v2/health                 # this
```

## Where /v2 differs from /v1, and why

Only where the difference earns itself:

- the list is called `locations`, not `stations`, because it has always
  contained addresses too, and each entry says which it is (`type`); `type=`
  narrows the answer;
- a coordinate is `{lat, lon}` in degrees taken straight from the upstream,
  instead of `x` and `y` computed from the Swiss grid - `x` was the latitude,
  which is the wrong way round, and the conversion lands about a metre off;
- `score` is gone: on this path it was always `null`;
- every field is always present, `null` when unknown, instead of keys that come
  and go;
- an empty question is a `400`, not an empty list that reads as "nothing
  found";
- errors are RFC 9457 problem documents, one shape for all of them, and an
  upstream `429` stays a `429` rather than becoming a fault of ours.

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
