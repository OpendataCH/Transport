"""Compare two /v1 hosts on about 500 random questions, before switching one for the other.

    python tools/compare_random.py sample.json --json report.json

`sample.json` holds random stations and real addresses, drawn on the timetable
server (stations: half weighted by departures, half uniform; addresses: the
nearest address to a random point 300-800 m from a random station). The cases
built from them, with a fixed seed:

- 150 connections stop to stop, 100 with an address at one end, 25 searched by
  arrival time;
- 100 station boards (one in five arrivals);
- 50 locations by name, 25 by address, 25 by coordinate.

For each case: the HTTP status of both, whether the answers have the same
shape (field names and types, null fitting any type), and a measure of the
values - earliest arrival and fastest duration for connections, departures
in common for boards, the first match and the distance between the places
found for locations.
"""

import argparse
import json
import math
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta

UA = "transport.opendata.ch comparison (transport@opendata.ch)"


def get(host: str, path: str, params: dict, retries: int = 4) -> tuple[int, dict | None]:
    url = f"{host}/v1/{path}?{urllib.parse.urlencode(params, doseq=True)}"
    for attempt in range(retries):
        try:
            request = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 429 and attempt + 1 < retries:
                time.sleep(15 * (attempt + 1))
                continue
            return error.code, None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            if attempt + 1 < retries:
                time.sleep(5)
                continue
            return 0, None
    return 0, None


def shape(value, path: str = "", out: dict | None = None) -> dict:
    out = defaultdict(set) if out is None else out
    if isinstance(value, dict):
        out[path].add("object")
        for key, item in value.items():
            shape(item, f"{path}.{key}", out)
    elif isinstance(value, list):
        out[path].add("list")
        for item in value:
            shape(item, f"{path}[]", out)
    elif value is None:
        out[path].add("null")
    elif isinstance(value, bool):
        out[path].add("bool")
    elif isinstance(value, (int, float)):
        out[path].add("number")
    else:
        out[path].add("string")
    return out


def shape_differences(a: dict, b: dict) -> list[str]:
    sa, sb = shape(a), shape(b)
    found = [f"only first: {k}" for k in sorted(set(sa) - set(sb))]
    found += [f"only second: {k}" for k in sorted(set(sb) - set(sa))]
    for key in sorted(set(sa) & set(sb)):
        x, y = sa[key] - {"null"}, sb[key] - {"null"}
        if x and y and x != y:
            found.append(f"type {key}: {sorted(x)} vs {sorted(y)}")
    return found


def metres(a: tuple, b: tuple) -> float | None:
    if None in (*a, *b):
        return None
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp, dl = p2 - p1, math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def minutes(duration: str) -> int:
    days, clock = duration.split("d")
    h, m, _ = clock.split(":")
    return int(days) * 1440 + int(h) * 60 + int(m)


def build_cases(sample: dict, day: date, seed: int) -> list[dict]:
    rng = random.Random(seed)
    stations, addresses = sample["stations"], sample["addresses"]

    def clock() -> str:
        return f"{rng.randint(6, 21):02d}:{rng.choice(['00', '10', '20', '30', '40', '50'])}"

    def pair() -> tuple[dict, dict]:
        a, b = rng.sample(stations, 2)
        return a, b

    cases = []
    for _ in range(150):
        a, b = pair()
        cases.append(
            {
                "kind": "connection",
                "label": f"{a['name']} → {b['name']}",
                "params": {
                    "from": a["name"],
                    "to": b["name"],
                    "date": str(day),
                    "time": clock(),
                    "limit": 4,
                },
            }
        )
    for i in range(100):
        address = addresses[i % len(addresses)]
        other = rng.choice(stations)
        ends = (address["text"], other["name"]) if i % 2 == 0 else (other["name"], address["text"])
        cases.append(
            {
                "kind": "connection-address",
                "label": f"{ends[0]} → {ends[1]}",
                "params": {
                    "from": ends[0],
                    "to": ends[1],
                    "date": str(day),
                    "time": clock(),
                    "limit": 4,
                },
            }
        )
    for _ in range(25):
        a, b = pair()
        cases.append(
            {
                "kind": "connection-arrival",
                "label": f"{a['name']} → {b['name']} (arrive)",
                "params": {
                    "from": a["name"],
                    "to": b["name"],
                    "date": str(day),
                    "time": clock(),
                    "limit": 4,
                    "isArrivalTime": 1,
                },
            }
        )
    for i in range(100):
        s = rng.choice(stations)
        params = {"station": s["name"], "limit": 10, "datetime": f"{day} {clock()}"}
        if i % 5 == 0:
            params["type"] = "arrival"
        cases.append(
            {
                "kind": "board",
                "label": s["name"] + (" (arrivals)" if i % 5 == 0 else ""),
                "params": params,
            }
        )
    for _ in range(50):
        s = rng.choice(stations)
        cases.append(
            {
                "kind": "location-name",
                "label": s["name"],
                "params": {"query": s["name"]},
                "expect": s,
            }
        )
    for i in range(25):
        address = addresses[(i + 100) % len(addresses)]
        cases.append(
            {
                "kind": "location-address",
                "label": address["text"],
                "params": {"query": address["text"], "type": "address"},
                "expect": address,
            }
        )
    for _ in range(25):
        s = rng.choice(stations)
        lat = s["lat"] + rng.uniform(-0.003, 0.003)
        lon = s["lon"] + rng.uniform(-0.004, 0.004)
        cases.append(
            {
                "kind": "location-coordinate",
                "label": f"{lat:.5f},{lon:.5f}",
                "params": {"x": f"{lat:.6f}", "y": f"{lon:.6f}"},
            }
        )
    return cases


def measure(case: dict, one: dict, two: dict) -> dict:
    kind = case["kind"]
    if kind.startswith("connection"):
        c1, c2 = one.get("connections") or [], two.get("connections") or []
        result = {"count": [len(c1), len(c2)]}
        if c1 and c2:
            arrive = case["params"].get("isArrivalTime")
            if arrive:
                # Latest departure that still arrives in time.
                d1 = max(c["from"]["departure"] for c in c1)[11:16]
                d2 = max(c["from"]["departure"] for c in c2)[11:16]
                result["latest_departure"] = [d1, d2]
            else:
                result["earliest_arrival"] = [
                    min(c["to"]["arrival"] for c in c1)[11:16],
                    min(c["to"]["arrival"] for c in c2)[11:16],
                ]
            result["fastest"] = [
                min(minutes(c["duration"]) for c in c1),
                min(minutes(c["duration"]) for c in c2),
            ]
            p1 = (one.get("from") or {}).get("coordinate") or {}
            p2 = (two.get("from") or {}).get("coordinate") or {}
            result["from_names"] = [
                (one.get("from") or {}).get("name"),
                (two.get("from") or {}).get("name"),
            ]
            result["to_names"] = [
                (one.get("to") or {}).get("name"),
                (two.get("to") or {}).get("name"),
            ]
            result["from_metres"] = metres((p1.get("x"), p1.get("y")), (p2.get("x"), p2.get("y")))
        return result
    if kind == "board":

        def key(j):
            return (j["stop"]["departure"], j.get("category"), j.get("number"))

        a = {key(j) for j in one.get("stationboard") or []}
        b = {key(j) for j in two.get("stationboard") or []}
        return {
            "count": [len(a), len(b)],
            "common": len(a & b),
            "station": [
                (one.get("station") or {}).get("name"),
                (two.get("station") or {}).get("name"),
            ],
        }
    s1, s2 = one.get("stations") or [], two.get("stations") or []
    result = {"count": [len(s1), len(s2)]}
    if s1 and s2:
        f1, f2 = s1[0], s2[0]
        result["first"] = [f1.get("name"), f2.get("name")]
        result["first_id_same"] = f1.get("id") == f2.get("id")
        if kind == "location-address":
            expect = case["expect"]
            c2 = f2.get("coordinate") or {}
            result["new_metres_from_address"] = metres(
                (expect["lat"], expect["lon"]), (c2.get("x"), c2.get("y"))
            )
        if kind == "location-coordinate":
            ids1 = [s.get("id") for s in s1 if s.get("id")]
            ids2 = [s.get("id") for s in s2 if s.get("id")]
            result["nearest_stop_same"] = bool(ids1 and ids2 and ids1[0] == ids2[0])
    return result


def verdict(case: dict, status: list, m: dict, shape_diff: list) -> str:
    if status != [200, 200]:
        return f"status {status[0]}/{status[1]}"
    kind = case["kind"]
    if kind.startswith("connection"):
        if m["count"][0] and not m["count"][1]:
            return "no connection in second"
        if m["count"][1] and not m["count"][0]:
            return "no connection in first"
        if not m["count"][0]:
            return "none in either"
        if "earliest_arrival" in m:
            a, b = m["earliest_arrival"]
            late = _diff(b, a)
            fast = m["fastest"][1] - m["fastest"][0]
            if late == 0 and fast <= 0:
                return "same or better"
            if late < 0 or fast < 0:
                return "second earlier or faster"
            return "second later by >15 min" if late > 15 else "second later by ≤15 min"
        a, b = m["latest_departure"]
        late = _diff(a, b)
        return (
            "same or better"
            if late <= 0
            else (
                "second earlier departure >15 min"
                if late > 15
                else "second earlier departure ≤15 min"
            )
        )
    if kind == "board":
        if not m["count"][0]:
            return "first empty"
        share = m["common"] / m["count"][0]
        return (
            "board ≥90% same"
            if share >= 0.9
            else "board 50-90% same"
            if share >= 0.5
            else "board <50% same"
        )
    if kind == "location-name":
        return "same first" if m.get("first_id_same") else "different first"
    if kind == "location-address":
        d = m.get("new_metres_from_address")
        if not m["count"][1]:
            return "address not found in second"
        return "address found (≤100 m)" if d is not None and d <= 100 else "address found far off"
    return "same nearest stop" if m.get("nearest_stop_same") else "different nearest stop"


def _diff(a: str, b: str) -> int:
    """Minutes from b to a, across midnight."""
    ma, mb = int(a[:2]) * 60 + int(a[3:]), int(b[:2]) * 60 + int(b[3:])
    d = ma - mb
    return d - 1440 if d > 720 else d + 1440 if d < -720 else d


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("sample")
    parser.add_argument("--first", default="https://transport.opendata.ch")
    parser.add_argument("--second", default="https://transport-new.opendata.ch")
    parser.add_argument("--json")
    parser.add_argument("--pause", type=float, default=1.0)
    parser.add_argument("--seed", type=int, default=20261005)
    args = parser.parse_args()

    sample = json.load(open(args.sample, encoding="utf-8"))
    today = datetime.now().date()
    day = today + timedelta(days=(1 if today.weekday() < 4 else 7 - today.weekday()))
    cases = build_cases(sample, day, args.seed)

    tally: dict[str, Counter] = defaultdict(Counter)
    shapes: Counter = Counter()
    results = []
    for n, case in enumerate(cases, 1):
        path = (
            "connections"
            if case["kind"].startswith("connection")
            else ("stationboard" if case["kind"] == "board" else "locations")
        )
        s1, one = get(args.first, path, case["params"])
        s2, two = get(args.second, path, case["params"])
        m = measure(case, one or {}, two or {}) if s1 == 200 and s2 == 200 else {}
        diff = shape_differences(one, two) if one is not None and two is not None else []
        for d in diff:
            shapes[(path, d)] += 1
        v = verdict(case, [s1, s2], m, diff)
        tally[case["kind"]][v] += 1
        results.append({**case, "status": [s1, s2], "measure": m, "shape": diff, "verdict": v})
        print(f"{n:3d} {case['kind']:<20} {v:<32} {case['label'][:70]}", flush=True)
        time.sleep(args.pause)

    print("\n== Summary")
    for kind, counts in tally.items():
        print(f"{kind}: {dict(counts.most_common())}")
    print("\n== Shape differences (path, difference, cases)")
    for (path, d), count in shapes.most_common():
        print(f"  {count:3d} {path}: {d}")
    if not shapes:
        print("  none")
    if args.json:
        json.dump(
            {"day": str(day), "results": results},
            open(args.json, "w"),
            ensure_ascii=False,
            indent=1,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
