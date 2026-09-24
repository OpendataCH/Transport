#!/usr/bin/env python3
"""Replay real traffic against both implementations and tally the differences.

Stage S5 in its working form. Two steps:

    # what shapes do real clients actually send?
    ssh OPEN-NINE 'cat ~/logs/transport.opendata.ch.access.log' \\
        | python tools/shadow.py sample --limit 60 > corpus.txt

    # ask both, compare, tally
    python tools/shadow.py compare corpus.txt \\
        --v1 https://transport.opendata.ch \\
        --v2 https://transport-new.opendata.ch

`--v1` defaults to the same host as `--v2`, which compares the two
implementations side by side. Pointing it at the live API instead compares
against the thing that actually serves the traffic.

**Sampling is by shape, not by popularity.** Requests are grouped by the set of
parameter names they carry, and a couple are taken from each group. Bern-Zürich
asked five hundred times teaches nothing the first one did not; a parameter
combination nobody expected teaches a great deal.

**A board or a route for *now* is not reproducible**, not even between two calls
to `/v1` itself: real-time delays move, `/v1` dates a missing prognosis to the
second of the request, and two calls either side of a minute boundary see
different departures. So a request that carries no time of its own is pinned to
a fixed minute two days out. That tests the parameter space - which is where the
risk is - and leaves the real-time path to the fixture tests. `--as-is` turns
the pinning off and shows what unpinned replay looks like.

**This is not a load test, and it spends the caller's own quota twice.** Every
query costs search.ch two requests - one per implementation - and both name the
same caller, so a comparison run throttles itself: the second request of a pair
is the one that comes back 429. That is why the pairs run one at a time with a
pause between them, and why a 429 is retried rather than recorded as a
difference. Keep the sample small (the default is 40), run it daily, and not in
a loop.

The honest way out of that limit is a stub: record one upstream answer and feed
it to both implementations. That is what S5 proper should do; this tool is the
version that needs nothing but two URLs.
"""

import argparse
import json
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta

from comparison import differences, field

# "GET /v1/locations?query=Bern HTTP/1.1" in a combined access log line.
REQUEST = re.compile(r'"GET (/v1/[^ "]*) HTTP/[0-9.]+"')

# The endpoints /v2 answers. Anything else in the log - the documentation, the
# examples, the statistics page - is the website, not the API.
ENDPOINTS = ("/v1/locations", "/v1/connections", "/v1/stationboard")

# Parameters that make a request reproducible. A request carrying none of them
# is pinned; one that carries any is replayed as it came.
TIME_PARAMETERS = ("date", "time", "datetime")


def sample(arguments) -> int:
    """Read access log lines and write a corpus of distinct request shapes."""
    targets = []
    for line in sys.stdin:
        found = REQUEST.search(line)
        if found and found.group(1).split("?")[0] in ENDPOINTS:
            targets.append(found.group(1))

    by_shape: dict[tuple, list[str]] = {}
    for target in targets:
        by_shape.setdefault(shape(target), []).append(target)

    random.seed(arguments.seed)
    chosen = []
    for _, group in sorted(by_shape.items()):
        chosen.extend(random.sample(group, min(arguments.per_shape, len(group))))
    random.shuffle(chosen)

    print(
        f"{len(targets)} requests, {len(by_shape)} distinct shapes, "
        f"{min(len(chosen), arguments.limit)} sampled",
        file=sys.stderr,
    )
    for shape_key, group in sorted(by_shape.items(), key=lambda item: -len(item[1]))[:12]:
        print(
            f"  {len(group):7}  {shape_key[0]}  {' '.join(shape_key[1:]) or '(no parameters)'}",
            file=sys.stderr,
        )

    for target in chosen[: arguments.limit]:
        print(target)
    return 0


def shape(target: str) -> tuple:
    """The endpoint and the set of parameter names - what makes a request a kind."""
    path, _, query = target.partition("?")
    names = sorted({name for name, _ in urllib.parse.parse_qsl(query, keep_blank_values=True)})
    return (path, *names)


def compare(arguments) -> int:
    corpus = [line.strip() for line in open(arguments.corpus) if line.strip()]
    pinned = datetime.now() + timedelta(days=2)

    throttled = 0

    def one(target: str):
        nonlocal throttled
        request = target if arguments.as_is else pin(target, pinned)

        for attempt in range(3):
            v1_status, v1_body, v1_raw = fetch(arguments.v1 + _v1(request, arguments))
            time.sleep(arguments.delay)
            if arguments.noise_floor:
                # Ask /v1 twice instead. Whatever differs is not a difference
                # between the implementations - it is the real-time data
                # moving underneath, and it is the floor this corpus can
                # measure to.
                v2_status, v2_body, v2_raw = fetch(arguments.v1 + _v1(request, arguments))
            else:
                v2_status, v2_body, v2_raw = fetch(
                    arguments.v2 + request.replace("/v1/", "/v2/", 1)
                )

            # Both sides name the same caller to search.ch, so a pair spends
            # the quota twice and the loser is whichever asked second. That is
            # the tool throttling itself, not a difference between the two.
            if 429 in (v1_status, v2_status) and attempt < 2:
                throttled += 1
                time.sleep(5 * (attempt + 1))
                continue
            break

        found = list(differences(v1_body, v2_body))
        if v1_status != v2_status:
            found.insert(0, f"(status): /v1 {v1_status} != /v2 {v2_status}")
        return request, found, v1_raw == v2_raw

    if arguments.workers > 1:
        with ThreadPoolExecutor(max_workers=arguments.workers) as pool:
            results = list(pool.map(one, corpus))
    else:
        results = [one(target) for target in corpus]

    fields: Counter[str] = Counter()
    identical = 0
    byte_identical = 0
    for request, found, same_bytes in results:
        byte_identical += same_bytes
        if not found:
            identical += 1
            if not arguments.quiet:
                print(f"  same  {request}")
            continue
        print(f"  DIFF  {request}")
        for difference in found[: arguments.show]:
            print(f"          {difference}")
        for difference in found:
            fields[field(difference)] += 1

    print(f"\n{identical} of {len(results)} answers identical")
    print(f"{byte_identical} of {len(results)} identical byte for byte")
    if throttled:
        print(f"({throttled} pairs were retried after a 429 from search.ch)")
    if fields:
        print("\ndiffering fields, by how often they differ:")
        for name, count in fields.most_common(20):
            print(f"  {count:6}  {name}")
    return 0 if identical == len(results) else 1


def _v1(request: str, arguments) -> str:
    """Where the reference implementation answers, under its own prefix."""
    return request.replace("/v1/", arguments.v1_prefix + "/", 1)


def pin(target: str, when: datetime) -> str:
    """Give a request a fixed time, unless it brought one.

    A station board takes `datetime`; a connection search takes `date` and
    `time`. Locations have no time at all and are left alone.
    """
    path, _, query = target.partition("?")
    parameters = urllib.parse.parse_qsl(query, keep_blank_values=True)
    if path == "/v1/locations" or any(name in TIME_PARAMETERS for name, _ in parameters):
        return target

    if path == "/v1/stationboard":
        parameters.append(("datetime", when.strftime("%Y-%m-%d 09:00")))
    else:
        parameters.append(("date", when.strftime("%Y-%m-%d")))
        parameters.append(("time", "09:00"))

    return path + "?" + urllib.parse.urlencode(parameters)


def fetch(url: str):
    """The status, the body as data, and the body as it came over the wire.

    The raw bytes matter: two answers can be the same document and not the same
    text. `json_encode` escapes non-ASCII and forward slashes, and a client
    matching on bytes would notice the day that stopped.
    """
    try:
        with urllib.request.urlopen(url, timeout=40) as response:
            raw = response.read()
            return response.status, body(raw, response.headers), raw
    except urllib.error.HTTPError as error:
        raw = error.read()
        return error.code, body(raw, error.headers), raw
    except Exception as error:  # noqa: BLE001 - a transport failure is a result too
        return 0, f"{type(error).__name__}: {error}", b""


def body(raw: bytes, headers) -> object:
    if "json" in headers.get("Content-Type", ""):
        return json.loads(raw)
    return raw.decode("utf-8", "replace").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)

    sampler = commands.add_parser("sample", help="read a log on stdin, write a corpus")
    sampler.add_argument("--limit", type=int, default=40, help="requests to keep (default 40)")
    sampler.add_argument("--per-shape", type=int, default=2, help="per distinct shape (default 2)")
    sampler.add_argument("--seed", type=int, default=0)
    sampler.set_defaults(run=sample)

    comparer = commands.add_parser("compare", help="replay a corpus against both")
    comparer.add_argument("corpus")
    comparer.add_argument("--v2", required=True, help="base URL of the Python service")
    comparer.add_argument("--v1", help="base URL of the PHP one (default: the same host)")
    comparer.add_argument(
        "--v1-prefix",
        default="/v1",
        help="the prefix the reference implementation answers under",
    )
    comparer.add_argument("--as-is", action="store_true", help="do not pin the time")
    comparer.add_argument(
        "--noise-floor",
        action="store_true",
        help="ask /v1 twice instead of comparing: what differs is the data, not the code",
    )
    comparer.add_argument(
        "--workers", type=int, default=1, help="pairs at a time; more means more 429s"
    )
    comparer.add_argument(
        "--delay", type=float, default=0.4, help="seconds between the two halves of a pair"
    )
    comparer.add_argument("--show", type=int, default=6, help="differences to print per request")
    comparer.add_argument("--quiet", action="store_true")
    comparer.set_defaults(run=compare)

    arguments = parser.parse_args()
    if arguments.command == "compare" and not arguments.v1:
        arguments.v1 = arguments.v2
    return arguments.run(arguments)


if __name__ == "__main__":
    sys.exit(main())
