#!/usr/bin/env python3
"""Ask /v1 and /v2 a hundred routing questions and report how they differ.

Where compare_sources.py checks shapes and a few samples, this one checks the
substance of routing across the country - cities, valleys, buses only, trams,
boats, cable cars, across the border, at night, on a Saturday, by arrival
time, via a stop - with the measures a traveller cares about:

- did both resolve the same two places,
- the same earliest arrival and the same first departure,
- how far apart the fastest travel times are,
- how many connections are identical (same departure and arrival).

    python tools/compare_routes.py --v1 https://transport.opendata.ch \\
        --v2 https://transport-new.opendata.ch --json report.json

Questions go to a fixed day two days out (and the Saturday after), so that
real time does not move the times between the two answers. Every /v1 question
costs one request of the caller's search.ch quota; they are sent one at a time.
"""

import argparse
import json
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta

# (from, to, extra parameters); the time is added per case.
ROUTES = [
    # Between cities and across the language border
    ("Zürich HB", "Genève", {}),
    ("Basel SBB", "Lugano", {}),
    ("Bern", "Lausanne", {}),
    ("St. Gallen", "Luzern", {}),
    ("Chur", "Zürich Flughafen", {}),
    ("Sion", "Brig", {}),
    ("Neuchâtel", "Biel/Bienne", {}),
    ("Fribourg", "Lausanne", {}),
    ("Winterthur", "Schaffhausen", {}),
    ("Olten", "Aarau", {}),
    ("Zug", "Arth-Goldau", {}),
    ("Lugano", "Locarno", {}),
    ("Bellinzona", "Airolo", {}),
    ("La Chaux-de-Fonds", "Delémont", {}),
    ("Solothurn", "Burgdorf", {}),
    ("Frauenfeld", "Kreuzlingen", {}),
    ("Genève-Aéroport", "Lausanne", {}),
    ("Zürich Flughafen", "Bern", {}),
    ("Yverdon-les-Bains", "Neuchâtel", {}),
    ("Porrentruy", "Basel SBB", {}),
    # Valleys, mountains, narrow gauge
    ("Thun", "Spiez", {}),
    ("Interlaken Ost", "Lauterbrunnen", {}),
    ("Montreux", "Gstaad", {}),
    ("Davos Platz", "St. Moritz", {}),
    ("Scuol-Tarasp", "Landquart", {}),
    ("Andermatt", "Disentis/Mustér", {}),
    ("Brig", "Zermatt", {}),
    ("Glarus", "Linthal", {}),
    ("Appenzell", "St. Gallen", {}),
    ("Herisau", "Wil SG", {}),
    ("Langenthal", "Huttwil", {}),
    ("Yverdon-les-Bains", "Sainte-Croix", {}),
    ("Nyon", "St-Cergue", {}),
    ("Schwyz", "Einsiedeln", {}),
    ("Altdorf UR", "Flüelen", {}),
    ("Stans", "Engelberg", {}),
    ("Sarnen", "Giswil", {}),
    ("Kandersteg", "Frutigen", {}),
    ("Aigle", "Les Diablerets", {}),
    ("Monthey", "Champéry", {}),
    ("Poschiavo", "Tirano", {}),
    ("Pontresina", "Samedan", {}),
    ("Lauterbrunnen", "Mürren", {}),
    ("Interlaken Ost", "Jungfraujoch", {}),
    ("Wengen", "Grindelwald", {}),
    ("Luzern", "Vitznau", {}),
    # Buses only
    ("Visp", "Saas-Fee", {}),
    ("Leuk", "Leukerbad", {}),
    ("Martigny", "Verbier", {}),
    ("Sargans", "Vaduz", {}),
    ("Chur", "Flims Dorf", {}),
    ("Lugano", "Tesserete", {}),
    ("Biel/Bienne", "Magglingen/Macolin", {}),
    # In town: tram, metro, bus
    ("Zürich, Bellevue", "Zürich, Paradeplatz", {}),
    ("Bern, Bahnhof", "Bern, Bärengraben", {}),
    ("Basel, Barfüsserplatz", "Basel, Messeplatz", {}),
    ("Genève, gare Cornavin", "Genève, Plainpalais", {}),
    ("Lausanne, Flon", "Lausanne, Ouchy-Olympique", {}),
    ("Luzern, Bahnhof", "Luzern, Verkehrshaus", {}),
    ("Winterthur, Hauptbahnhof", "Winterthur, Seen", {}),
    ("St. Gallen, Marktplatz", "St. Gallen, Neudorf", {}),
    # Across the border
    ("Basel SBB", "Mulhouse", {}),
    ("Genève", "Annemasse", {}),
    ("Lugano", "Como S. Giovanni", {}),
    ("Schaffhausen", "Singen (Hohentwiel)", {}),
    ("Buchs SG", "Feldkirch", {}),
    ("St. Margrethen", "Bregenz", {}),
    ("Chiasso", "Mendrisio", {}),
    # By number, via, arrival
    ("8503000", "8507000", {}),
    ("8500010", "8505000", {}),
    ("Zürich HB", "Genève", {"via[]": "Bern"}),
    ("Basel SBB", "Chur", {"via[]": "Zürich HB"}),
    ("Bern", "Zürich HB", {"isArrivalTime": "1"}),
    ("Lausanne", "Zermatt", {"isArrivalTime": "1"}),
    ("Luzern", "Engelberg", {"isArrivalTime": "1"}),
    ("Basel SBB", "Lugano", {"isArrivalTime": "1"}),
    ("Zürich HB", "Chur", {"transportations[]": "train"}),
    ("Zürich HB", "Zürich Flughafen", {"transportations[]": "bus"}),
]

# The same handful at other hours, and on a Saturday.
TIMES = [
    ("Zürich HB", "Bern", "06:30"),
    ("Zürich HB", "Bern", "23:30"),
    ("Genève", "Lausanne", "00:30"),
    ("Basel SBB", "Zürich HB", "05:15"),
    ("Lugano", "Bellinzona", "22:45"),
    ("Chur", "Arosa", "18:00"),
    ("Brig", "Domodossola", "12:00"),
    ("Luzern", "Interlaken Ost", "17:30"),
    ("St. Gallen", "Zürich HB", "07:10"),
    ("Bern", "Grindelwald", "08:20"),
]
SATURDAY = [
    ("Zürich HB", "Davos Platz"),
    ("Bern", "Zermatt"),
    ("Lausanne", "Verbier"),
    ("Basel SBB", "Engelberg"),
    ("Luzern", "Flüelen"),
]

BOARDS = [
    "Grindelwald",
    "Zermatt",
    "Lugano, Centro",
    "Brig",
    "Arosa",
    "Wengen",
    "Sion",
    "Basel Bad Bf",
    "Genève-Aéroport",
    "Zürich Flughafen",
    "Schaffhausen",
    "St. Moritz",
    "Andermatt",
    "Luzern, Bahnhof",
    "Zürich, Central",
    "Bern, Zytglogge",
    "Locarno",
    "Vitznau",
    "Lausanne, Flon",
    "Appenzell",
]


def get(base: str, path: str, params) -> tuple[int, dict | None]:
    url = f"{base.rstrip('/')}{path}?{urllib.parse.urlencode(params)}"
    request = urllib.request.Request(url, headers={"User-Agent": "transport-compare-routes"})
    for attempt in range(4):
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as error:
            if error.code == 429 and attempt < 3:
                time.sleep(30)
                continue
            return error.code, None
        except (urllib.error.URLError, TimeoutError) as error:
            return 0, {"error": str(error)}
    return 429, None


def minutes(iso: str) -> int:
    return int(datetime.strptime(iso, "%Y-%m-%dT%H:%M:%S%z").timestamp() // 60)


def duration(text: str) -> int:
    days, clock = text.split("d")
    h, m, _ = clock.split(":")
    return int(days) * 1440 + int(h) * 60 + int(m)


def compare_connections(one: dict, two: dict) -> dict:
    a = one.get("connections") or []
    b = two.get("connections") or []
    pairs_a = {(c["from"]["departure"], c["to"]["arrival"]) for c in a}
    pairs_b = {(c["from"]["departure"], c["to"]["arrival"]) for c in b}
    result = {
        "from": [(one.get("from") or {}).get("name"), (two.get("from") or {}).get("name")],
        "to": [(one.get("to") or {}).get("name"), (two.get("to") or {}).get("name")],
        "same_places": (one.get("from") or {}).get("id") == (two.get("from") or {}).get("id")
        and (one.get("to") or {}).get("id") == (two.get("to") or {}).get("id"),
        "count": [len(a), len(b)],
        "identical": len(pairs_a & pairs_b),
    }
    if a and b:
        result["earliest_arrival"] = [
            min(c["to"]["arrival"] for c in a)[11:16],
            min(c["to"]["arrival"] for c in b)[11:16],
        ]
        result["first_departure"] = [
            a[0]["from"]["departure"][11:16],
            b[0]["from"]["departure"][11:16],
        ]
        result["fastest"] = [
            min(duration(c["duration"]) for c in a),
            min(duration(c["duration"]) for c in b),
        ]
        result["fastest_v1"] = next(
            {
                "dep": c["from"]["departure"][11:16],
                "arr": c["to"]["arrival"][11:16],
                "products": c["products"],
            }
            for c in a
            if duration(c["duration"]) == result["fastest"][0]
        )
        result["fastest_v2"] = next(
            {
                "dep": c["from"]["departure"][11:16],
                "arr": c["to"]["arrival"][11:16],
                "products": c["products"],
            }
            for c in b
            if duration(c["duration"]) == result["fastest"][1]
        )
    return result


def verdict(r: dict) -> str:
    if r.get("status") != [200, 200]:
        return "error"
    if not r["count"][0] and not r["count"][1]:
        return "both empty"
    if not r["count"][1]:
        return "v2 empty"
    if not r["count"][0]:
        return "v1 empty"
    if not r["same_places"]:
        return "different places"
    if r["identical"] == r["count"][0] == r["count"][1]:
        return "identical"
    if (
        r["earliest_arrival"][0] == r["earliest_arrival"][1]
        and r["first_departure"][0] == r["first_departure"][1]
    ):
        return "same best, others differ"
    if r["earliest_arrival"][0] == r["earliest_arrival"][1]:
        return "same earliest arrival"
    if r["fastest"][1] <= r["fastest"][0]:
        return "different, v2 as fast or faster"
    return "different, v1 faster"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--v1", default="https://transport.opendata.ch")
    parser.add_argument("--v2", default="https://transport-new.opendata.ch")
    parser.add_argument("--pause", type=float, default=1.5)
    parser.add_argument("--json", help="write every case and its measures here")
    parser.add_argument(
        "--random",
        metavar="FILE",
        help="more cases: one `from|to` pair per line, each at a random hour "
        "(random_pairs.txt next to this script: 40 pairs of served stops, drawn "
        "weighted by departures from the PROD timetable on 4.10.2026)",
    )
    parser.add_argument("--seed", type=int, default=20261004, help="for the random hours")
    arguments = parser.parse_args()

    day = datetime.now() + timedelta(days=2)
    saturday = day + timedelta(days=(5 - day.weekday()) % 7 or 7)
    cases = [
        (
            {
                "from": f,
                "to": t,
                "date": day.strftime("%Y-%m-%d"),
                "time": "09:00",
                "limit": "4",
                **extra,
            },
            f"{f} → {t}" + (f" {extra}" if extra else ""),
        )
        for f, t, extra in ROUTES
    ]
    cases += [
        (
            {"from": f, "to": t, "date": day.strftime("%Y-%m-%d"), "time": hh, "limit": "4"},
            f"{f} → {t} {hh}",
        )
        for f, t, hh in TIMES
    ]
    cases += [
        (
            {
                "from": f,
                "to": t,
                "date": saturday.strftime("%Y-%m-%d"),
                "time": "10:00",
                "limit": "4",
            },
            f"{f} → {t} Sa 10:00",
        )
        for f, t in SATURDAY
    ]

    if arguments.random:
        rng = random.Random(arguments.seed)
        with open(arguments.random) as pairs:
            for line in pairs:
                if "|" not in line:
                    continue
                f, t = (part.strip() for part in line.split("|", 1))
                hh = f"{rng.randint(5, 23):02d}:{rng.choice(['00', '15', '30', '45'])}"
                params = {
                    "from": f,
                    "to": t,
                    "date": day.strftime("%Y-%m-%d"),
                    "time": hh,
                    "limit": "4",
                }
                cases.append((params, f"random: {f} → {t} {hh}"))

    results = []
    tally = Counter()
    for params, label in cases:
        s1, one = get(arguments.v1, "/v1/connections", params)
        s2, two = get(arguments.v2, "/v2/connections", params)
        r = {"case": label, "status": [s1, s2]}
        if s1 == 200 and s2 == 200:
            r.update(compare_connections(one, two))
        r["verdict"] = verdict(r)
        tally[r["verdict"]] += 1
        results.append(r)
        line = f"{r['verdict']:<32} {label}"
        if "earliest_arrival" in r:
            arrival, fastest = r["earliest_arrival"], r["fastest"]
            line += (
                f"  | arr {arrival[0]}/{arrival[1]}  fastest {fastest[0]}/{fastest[1]} min"
                f"  same {r['identical']}/{r['count'][0]}"
            )
        elif r["verdict"] == "different places":
            line += f"  | {r['from']} {r['to']}"
        print(line, flush=True)
        time.sleep(arguments.pause)

    boards = []
    for station in BOARDS:
        params = {"station": station, "limit": "15", "datetime": day.strftime("%Y-%m-%d 09:00")}
        s1, one = get(arguments.v1, "/v1/stationboard", params)
        s2, two = get(arguments.v2, "/v2/stationboard", params)
        r = {"case": station, "status": [s1, s2]}
        if s1 == 200 and s2 == 200:
            key = lambda j: (j["stop"]["departure"], j["category"], j["number"])  # noqa: E731
            a = {key(j) for j in one["stationboard"]}
            b = {key(j) for j in two["stationboard"]}
            r.update(
                station=[
                    (one.get("station") or {}).get("name"),
                    (two.get("station") or {}).get("name"),
                ],
                count=[len(a), len(b)],
                matched=len(a & b),
            )
        boards.append(r)
        count = r.get("count", ["-", "-"])
        print(
            f"board {station:<22} {r.get('station')}  v1 {count[0]} v2 {count[1]}"
            f" matched {r.get('matched', '-')}",
            flush=True,
        )
        time.sleep(arguments.pause)

    print("\nConnections:", dict(tally.most_common()))
    matched = sum(b.get("matched", 0) for b in boards)
    total_v1 = sum(b.get("count", [0])[0] for b in boards)
    print(f"Boards: {matched} of {total_v1} departures of /v1 also in /v2")
    if arguments.json:
        with open(arguments.json, "w") as out:
            json.dump(
                {"day": day.strftime("%Y-%m-%d"), "connections": results, "boards": boards},
                out,
                ensure_ascii=False,
                indent=1,
            )
    return 0


if __name__ == "__main__":
    sys.exit(main())
