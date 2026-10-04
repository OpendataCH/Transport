#!/usr/bin/env python3
"""Ask /v1 (search.ch) and /v2 (our timetable) the same thing; report how they differ.

The two answer from different sources, so their values are not expected to be
equal. What should be equal is the shape - the same keys, the same types,
null and missing kept apart - and the substance: the same station first, the
same departures. The report shows both.

    python tools/compare_sources.py --v1 https://transport.opendata.ch --v2 http://localhost:8010

Every /v1 question costs one request of the caller's search.ch quota; they are
sent one at a time, with a pause.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta

from comparison import differences, field

STATIONS = [
    "Bern",
    "Zürich HB",
    "Basel",
    "Genève",
    "Lausanne",
    "Luzern",
    "Lugano",
    "Chur",
    "Winterthur",
    "St. Gallen",
    "Bellevue",
    "Zürich, Bellevue",
    "Bern, Zytglogge",
    "Interlaken Ost",
    "Kehrsiten-Bürgenstock",
]

COORDINATES = [(47.002347, 8.379934), (46.948, 7.4391), (46.388653, 6.238729)]

BOARDS = [
    {"id": "8507000"},
    {"id": "8503000"},
    {"station": "Basel SBB"},
    {"station": "Genève"},
    {"station": "Lugano"},
    {"station": "Bern, Zytglogge"},
    {"station": "Zürich, Bellevue"},
    {"station": "Interlaken Ost"},
    {"station": "Brienz BE"},
    {"station": "Kehrsiten-Bürgenstock"},
    {"station": "Bern", "type": "arrival"},
    {"station": "Bern, Bahnhof", "transportations[]": "bus"},
]


def get(base: str, path: str, params: dict) -> dict | None:
    url = f"{base.rstrip('/')}{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "transport-compare-sources"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 429 and attempt < 2:
                time.sleep(20)
                continue
            return {"__error__": error.code}
        except urllib.error.URLError as error:
            return {"__error__": str(error.reason)}
    return None


def shape(value):
    """The answer with its values replaced by their types; lists by their first entry."""
    if isinstance(value, dict):
        return {key: shape(item) for key, item in value.items()}
    if isinstance(value, list):
        return [shape(value[0])] if value else []
    return type(value).__name__


class Report:
    def __init__(self) -> None:
        self.shape = Counter()
        self.notes: list[str] = []

    def compare_shape(self, one, other) -> None:
        if not one or not other or "__error__" in one or "__error__" in other:
            return
        for difference in differences(shape(one), shape(other)):
            self.shape[f"{field(difference)}  {difference.split(':', 1)[1].strip()}"] += 1

    def note(self, text: str) -> None:
        self.notes.append(text)
        print(text)


def compare_locations(report: Report, v1: str, v2: str, pause: float) -> None:
    print("\n## Locations by name\n")
    same_first = 0
    for name in STATIONS:
        one = get(v1, "/v1/locations", {"query": name})
        two = get(v2, "/v2/locations", {"query": name})
        report.compare_shape(one, two)
        a = [(s["id"], s["name"]) for s in (one or {}).get("stations", [])]
        b = [(s["id"], s["name"]) for s in (two or {}).get("stations", [])]
        first_same = bool(a and b and a[0][0] == b[0][0])
        same_first += first_same
        overlap = len({i for i, _ in a} & {i for i, _ in b})
        mark = "=" if first_same else "≠"
        report.note(
            f"{mark} {name!r}: v1 first {a[0][1] if a else '-'!r}, v2 first "
            f"{b[0][1] if b else '-'!r}; {overlap}/{len(a)} of v1's ids also in v2"
        )
        if not first_same:
            report.note(f"    v1: {[n for _, n in a[:5]]}")
            report.note(f"    v2: {[n for _, n in b[:5]]}")
        time.sleep(pause)
    report.note(f"\nSame first station: {same_first}/{len(STATIONS)}")

    print("\n## Locations by coordinate\n")
    for lat, lon in COORDINATES:
        one = get(v1, "/v1/locations", {"x": lat, "y": lon})
        two = get(v2, "/v2/locations", {"x": lat, "y": lon})
        report.compare_shape(one, two)
        a = [(s["name"], s["distance"]) for s in (one or {}).get("stations", [])]
        b = [(s["name"], s["distance"]) for s in (two or {}).get("stations", [])]
        report.note(f"({lat}, {lon})\n    v1: {a[:4]}\n    v2: {b[:4]}")
        time.sleep(pause)


def journey_key(journey: dict) -> tuple:
    return (journey["stop"]["departure"], journey.get("category"), journey.get("number"))


def compare_boards(report: Report, v1: str, v2: str, when: str, pause: float) -> None:
    print(f"\n## Station boards at {when}\n")
    totals = Counter()
    mismatched = Counter()
    for params in BOARDS:
        query = {"limit": "15", "datetime": when, **params}
        one = get(v1, "/v1/stationboard", query)
        two = get(v2, "/v2/stationboard", query)
        report.compare_shape(one, two)
        a = {journey_key(j): j for j in (one or {}).get("stationboard", [])}
        b = {journey_key(j): j for j in (two or {}).get("stationboard", [])}
        both = a.keys() & b.keys()
        totals["v1"] += len(a)
        totals["v2"] += len(b)
        totals["matched"] += len(both)
        for key in both:
            for name in ("name", "to", "operator"):
                if a[key].get(name) != b[key].get(name):
                    mismatched[name] += 1
                    if mismatched[name] <= 3:
                        report.note(f"    {name}: v1 {a[key].get(name)!r} v2 {b[key].get(name)!r}")
            if a[key]["stop"]["platform"] != b[key]["stop"]["platform"]:
                mismatched["platform"] += 1
            if a[key]["stop"]["location"]["id"] != b[key]["stop"]["location"]["id"]:
                mismatched["terminal id"] += 1
            if [s["station"]["id"] for s in a[key]["passList"][1:]] != [
                s["station"]["id"] for s in b[key]["passList"][1:]
            ]:
                mismatched["passList stops"] += 1
        label = ", ".join(f"{k}={v}" for k, v in params.items())
        station = ((one or {}).get("station") or {}).get("name")
        station2 = ((two or {}).get("station") or {}).get("name")
        report.note(
            f"{label}: v1 {station!r} {len(a)}, v2 {station2!r} {len(b)}, matched {len(both)}"
        )
        only_one = sorted(a.keys() - b.keys())[:3]
        only_two = sorted(b.keys() - a.keys())[:3]
        if only_one:
            report.note(f"    only v1: {only_one}")
        if only_two:
            report.note(f"    only v2: {only_two}")
        time.sleep(pause)

    report.note(
        f"\nJourneys: v1 {totals['v1']}, v2 {totals['v2']}, matched by (time, category, line) "
        f"{totals['matched']}"
    )
    for name, count in mismatched.most_common():
        report.note(f"  of the matched, {name} differs in {count}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--v1", default="https://transport.opendata.ch")
    parser.add_argument("--v2", default="http://localhost:8000")
    parser.add_argument("--pause", type=float, default=1.5, help="seconds between /v1 calls")
    parser.add_argument(
        "--when",
        default=(datetime.now() + timedelta(days=2)).strftime("%Y-%m-%d 09:00"),
        help="board time; two days out by default, so that real time does not enter",
    )
    arguments = parser.parse_args()

    report = Report()
    compare_locations(report, arguments.v1, arguments.v2, arguments.pause)
    compare_boards(report, arguments.v1, arguments.v2, arguments.when, arguments.pause)

    print("\n## Shape differences (field, kind, how often)\n")
    if not report.shape:
        print("none")
    for line, count in report.shape.most_common():
        print(f"{count:4}  {line}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
