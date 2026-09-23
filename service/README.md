# The Python service (`/v2`)

A FastAPI application that runs **beside** the PHP one, behind the same
hostname. nginx picks between them by path prefix: `/v2/` comes here,
everything else stays with PHP. Nothing about `/v1` changes because this
service exists.

The plan and its stages are in the wiki:
[Plan: a Python service beside the PHP one](https://gitlab.com/opendata.ch/Transport/-/wikis/Plan-v2-FastAPI).

**This service answers `/v1`** - the contract every client already speaks -
and `/v2` as an alias of the same routes. The PHP implementation keeps
answering under **`/v1-old`**, unrouted from the name clients use, so the two
can still be compared and one line of nginx puts it back.

| | |
| --- | --- |
| `/v1/locations`, `/v1/stationboard`, `/v1/connections`, `/v1/` | the API |
| `/v1/health` | which build is running, and in which timezone |
| `/v1/docs`, `/v1/documentation`, `/v1/openapi.json` | Swagger UI, ReDoc, OpenAPI 3.1 |
| `/v2/…` | the same routes, undocumented, so old bookmarks keep working |

What is **not** here, on purpose: the website around the API - `/docs.html`,
`/swagger.json` (the generated Swagger 2.0 document), `/examples/`,
`/showcase.html`, `robots.txt`. Those still come from the PHP container.

## Running it

```sh
cd service
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
pytest
uvicorn transport_api.main:app --reload --port 8000
```

```sh
curl -s localhost:8000/v1/health
{"status":"ok","version":"dev","timezone":"Europe/Zurich","time":"2026-09-21T23:41:02.123456+02:00"}

curl -s 'localhost:8000/v1/locations?query=Bern'
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

`tools/shadow.py` does the same with **real traffic**: it samples the live
access log by request *shape* rather than popularity, then replays the corpus
against both. `--noise-floor` asks `/v1` twice instead, which says how much of
what is left is the data moving rather than the code differing.

```sh
ssh OPEN-NINE 'cat ~/logs/transport.opendata.ch.access.log' \
    | python tools/shadow.py sample --limit 40 > corpus.txt
python tools/shadow.py compare corpus.txt \
    --v1 https://transport.opendata.ch --v2 https://transport-new.opendata.ch
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
curl -s 'localhost:8000/v1/locations?query=Bern'      # this
curl -s 'localhost:8000/v1-old/locations?query=Bern'  # PHP
curl -s localhost:8000/docs.html                      # PHP, the website
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
- `fields[]` filters the answer, narrow paths beating broad ones, and an object
  left with no keys comes back as `[]` rather than `{}`;
- a repeated parameter without brackets keeps only its **last** value, because
  that is what PHP's `parse_str` does;
- the JSON is encoded as `json_encode` encodes it - non-ASCII escaped, forward
  slashes escaped - so the answer is not merely the same document but the same
  bytes;
- an empty question answers an empty list, not a 400;
- errors keep the `{"errors": [{"message": …}]}` envelope, and an upstream
  `429` is passed through as a `429`.

What is deliberately *not* the same: `/v2/` reports version `2.0`, and the
machine-readable description is OpenAPI 3.1 at `/v2/openapi.json` rather than
the generated Swagger 2.0 document `/v1` serves. Neither is part of the data a
client reads.

## Four things this service must keep doing

- **Not the website.** Every route lives under `/v1` or `/v2`, and
  `tests/test_routing.py` asserts that `/`, `/docs.html`, `/swagger.json` and
  the rest return 404 here. They are the PHP container's, and still have to be
  served by something.
- **Europe/Zurich.** The image installs `tzdata` and sets `TZ`; `/v2/health`
  reports the zone and a timestamp with its offset, so a container that came up
  on UTC says so in the smoke test rather than in the data months later.
- **Forward the caller.** search.ch rate-limits on the IP address and
  User-Agent we name, plus the optional `key`. Lose them and every caller in
  the world shares one bucket and throttles each other, with a rise in 429s as
  the only symptom. `X-Forwarded-For` is read in the application, not by a
  uvicorn flag, so that a test can exercise it.
- **Count for /stats.php.** With `REDIS_URL` set (the Redis the PHP writes to,
  e.g. `redis://redis:6379/0`), every answered request is counted in the PHP's
  own keys - calls, errors under the PHP exception names, resources, hourly
  buckets with the 429s - plus the kind of client, the stations and pairs
  asked for, and distinct clients as day-keyed hashes. `statistics.py` explains
  each; the client kinds are listed there and in `lib/Transport/Statistics.php`
  and must stay the same in both. Unset, nothing is counted. A Redis failure
  never costs an answer.

## The image

Built by `.gitlab-ci.yml` on every push to
`registry.gitlab.com/opendata.ch/transport/service`, tagged with the short
commit SHA and — on the default branch — `latest`. It is a second image beside
the PHP one and deploys and rolls back independently of it.
