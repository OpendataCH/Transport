# The Python service (`/v2`)

A FastAPI application that runs **beside** the PHP one, behind the same
hostname. nginx picks between them by path prefix: `/v2/` comes here,
everything else stays with PHP. Nothing about `/v1` changes because this
service exists.

The plan and its stages are in the wiki:
[Plan: a Python service beside the PHP one](https://gitlab.com/opendata.ch/Transport/-/wikis/Plan-v2-FastAPI).
This directory is stage **S0**: the routing and both services alive at once.
It answers `/v2/health` and nothing else.

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
```

Or through the development compose project at the repository root, which brings
up the PHP application and this one together on port 8000, exactly as the
servers arrange them:

```sh
docker compose up --build
curl -s localhost:8000/v1/locations?query=Bern   # PHP
curl -s localhost:8000/v2/health                 # this
```

## Two things this service must keep doing

- **Only `/v2`.** Every route lives under that prefix and `tests/test_routing.py`
  asserts that the `/v1` surface returns 404 here. A location block written too
  broadly would otherwise shadow the contract the PHP application owns with a
  half-built answer.
- **Europe/Zurich.** The image installs `tzdata` and sets `TZ`; `/v2/health`
  reports the zone and a timestamp with its offset, so a container that came up
  on UTC says so in the smoke test rather than in the data months later.

## The image

Built by `.gitlab-ci.yml` on every push to
`registry.gitlab.com/opendata.ch/transport/service`, tagged with the short
commit SHA and — on the default branch — `latest`. It is a second image beside
the PHP one and deploys and rolls back independently of it.
