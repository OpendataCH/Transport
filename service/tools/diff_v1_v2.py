#!/usr/bin/env python3
"""Ask /v1 and /v2 the same thing and report where they disagree.

The middle layer of the testing plan, in its smallest useful form: a request is
sent to both implementations of the same host and the two JSON answers are
compared structurally - order-aware for lists, order-insensitive for object
keys, and `null` kept strictly apart from a missing key.

    python tools/diff_v1_v2.py https://test-transport-new.opendata.ch
    python tools/diff_v1_v2.py https://transport-new.opendata.ch --quiet

It is not a load test: the queries below are a handful, and both sides call
search.ch once each. Anything that needs volume belongs against a stub.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta

from comparison import differences

# Enough shapes to catch a mapping mistake: a plain name, a name with an
# umlaut, one that matches nothing, a coordinate search (distances, an address
# entry without coordinates), and the empty question.
LOCATION_QUERIES = [
    "/locations?query=Bern",
    "/locations?query=Z%C3%BCrich%20HB",
    "/locations?query=Gen%C3%A8ve",
    "/locations?query=xyzzy-nothing-matches",
    "/locations?x=47.002347&y=8.379934",
    "/locations?x=46.388653&y=6.238729",
    "/locations?query=Bern&type=station",
    "/locations",
]


def stationboard_queries() -> list[str]:
    """Boards for a fixed minute two days out.

    Deliberately not "now". A live board carries real-time delays that change
    between the two calls, and /v1 dates a missing prognosis to the moment of
    the request - so comparing two live boards compares two different seconds.
    Two days ahead there is no real-time data, the timetable is fixed, and any
    difference that shows up is a difference in the mapping.
    """
    when = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    return [
        f"/stationboard?station=Bern&limit=5&datetime={when}%2009:00",
        f"/stationboard?station=Z%C3%BCrich%20HB&limit=3&datetime={when}%2009:00",
        f"/stationboard?id=8503000&limit=3&datetime={when}%2009:00",
        f"/stationboard?station=Bern&limit=3&type=arrival&datetime={when}%2009:00",
        f"/stationboard?station=Bern&limit=3&transportations[]=tram&datetime={when}%2009:00",
        f"/stationboard?station=Lugano&limit=2&datetime={when}%2023:50",
        "/stationboard?station=Bern&limit=421",
        "/stationboard",
    ]


def connection_queries() -> list[str]:
    """Journeys for a fixed minute two days out, for the same reason.

    Connections carry real-time delays too, and a connection search run twice
    around a minute boundary returns a different first departure.
    """
    when = (datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d")
    return [
        f"/connections?from=Bern&to=Z%C3%BCrich&date={when}&time=09:00",
        f"/connections?from=Lausanne&to=Gen%C3%A8ve&date={when}&time=09:00&limit=6",
        f"/connections?from=Bern&to=Z%C3%BCrich&date={when}&time=09:00&page=2&limit=3",
        f"/connections?from=Bern&to=Z%C3%BCrich&date={when}&time=09:00&isArrivalTime=1",
        f"/connections?from=Bern&to=Gen%C3%A8ve&via[]=Fribourg&date={when}&time=09:00",
        f"/connections?from=Z%C3%BCrich%20HB&to=Uetliberg&date={when}&time=09:00",
        f"/connections?from=Bern&to=Z%C3%BCrich&date={when}&time=09:00&transportations[]=train",
        # The shapes that never reach search.ch, and the one that fails there.
        "/connections?from=Bern&to=Z%C3%BCrich&limit=17",
        "/connections?from=Bern",
        "/connections?from=xyzzy-nowhere&to=zzzz-nowhere",
    ]


def fetch(url: str):
    """The status and the body - as data when it is JSON, as text when it is not.

    Not every answer is a document: /v1 refuses an over-large `limit` with a
    bare string, and that refusal has to match too.
    """
    try:
        with urllib.request.urlopen(url, timeout=30) as response:
            return response.status, _body(response.read(), response.headers)
    except urllib.error.HTTPError as error:
        return error.code, _body(error.read(), error.headers)


def _body(raw: bytes, headers) -> object:
    if "json" in headers.get("Content-Type", ""):
        return json.loads(raw)
    return raw.decode("utf-8", "replace").strip()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("host", help="e.g. https://test-transport-new.opendata.ch")
    parser.add_argument("--quiet", action="store_true", help="only the tally")
    args = parser.parse_args()

    queries = LOCATION_QUERIES + stationboard_queries() + connection_queries()

    identical = 0
    for query in queries:
        v1_status, v1_body = fetch(args.host + "/v1" + query)
        v2_status, v2_body = fetch(args.host + "/v2" + query)

        found = list(differences(v1_body, v2_body))
        if v1_status != v2_status:
            found.insert(0, f": status {v1_status} in /v1, {v2_status} in /v2")

        if not found:
            identical += 1
            if not args.quiet:
                print(f"  same  {query}")
        else:
            print(f"  DIFF  {query}")
            for difference in found[:20]:
                print(f"          {difference}")

    print(f"\n{identical} of {len(queries)} answers identical")
    return 0 if identical == len(queries) else 1


if __name__ == "__main__":
    sys.exit(main())
