"""`/v2/map/*` against a stand-in router."""

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from transport_api import errors
from transport_api.timetable import map as tmap

SEGMENT = {
    "trips": [{"tripId": "20261005_08:00_ch_t1", "displayName": "IC 5"}],
    "mode": "RAIL",
    "distance": 1000.0,
    "from": {
        "name": "Alpha",
        "stopId": "ch_ch:1:sloid:1:1:1",
        "parentId": "ch_Parentch:1:sloid:1",
        "lat": 47.0,
        "lon": 7.0,
    },
    "to": {"name": "Beta", "stopId": "ch_8500002", "lat": 47.1, "lon": 7.1},
    "departure": "2026-10-05T06:02:00Z",
    "arrival": "2026-10-05T06:10:00Z",
    "scheduledDeparture": "2026-10-05T06:00:00Z",
    "scheduledArrival": "2026-10-05T06:08:00Z",
    "realTime": True,
    "polyline": "abc",
}


class FakeMotis:
    def __init__(self):
        self.calls = []

    async def get(self, path, params):
        self.calls.append((path, params))
        if path == "/api/v6/map/trips":
            return [SEGMENT]
        if path == "/api/v6/one-to-all":
            return {
                "all": [
                    {
                        "place": {
                            "name": "Beta",
                            "stopId": "ch_8500002:0:1",
                            "parentId": "ch_8500002",
                            "lat": 47.1,
                            "lon": 7.1,
                        },
                        "duration": 12,
                        "k": 1,
                    },
                    {
                        "place": {
                            "name": "Beta",
                            "stopId": "ch_8500002:0:2",
                            "parentId": "ch_8500002",
                            "lat": 47.1,
                            "lon": 7.1,
                        },
                        "duration": 9,
                        "k": 0,
                    },
                ]
            }
        if path == "/api/v6/trip":
            return {
                "legs": [
                    {
                        "displayName": "IC 5",
                        "headsign": "Beta",
                        "agencyName": "SBB",
                        "mode": "RAIL",
                        "realTime": True,
                        "legGeometry": {"points": "xyz"},
                        "from": SEGMENT["from"],
                        "to": SEGMENT["to"],
                        "intermediateStops": [],
                    }
                ]
            }
        raise AssertionError(path)


@pytest.fixture
def api():
    tmap._cache.clear()
    motis = FakeMotis()
    app = FastAPI()
    errors.install(app)
    app.include_router(tmap.router, prefix="/v2")
    app.dependency_overrides[tmap.get_motis] = lambda: motis
    app.dependency_overrides[tmap.db.get_pool] = lambda: None
    with TestClient(app) as client:
        client.motis = motis
        yield client


def test_vehicles_carry_the_segment_and_its_delay(api):
    answer = api.get("/v2/map/vehicles", params={"min": "46.95,7.40", "max": "47.05,7.50"}).json()
    segment = answer["segments"][0]
    assert segment["name"] == "IC 5"
    assert segment["delay"] == 2
    assert segment["from"]["id"] == "8500001"
    assert segment["to"]["id"] == "8500002"


def test_vehicles_are_asked_once_per_box_and_minute(api):
    for _ in range(3):
        api.get("/v2/map/vehicles", params={"min": "46.951,7.401", "max": "47.05,7.5"})
    assert len(api.motis.calls) == 1


def test_a_box_too_large_is_refused(api):
    response = api.get("/v2/map/vehicles", params={"min": "45.8,5.9", "max": "47.8,10.5"})
    assert response.status_code == 400


def test_reachable_keeps_each_stop_once_at_its_best(api):
    answer = api.get("/v2/map/reachable", params={"x": 46.948, "y": 7.439, "minutes": 30}).json()
    assert answer["stops"] == [
        {"id": "8500002", "name": "Beta", "lat": 47.1, "lon": 7.1, "minutes": 9, "transfers": 0}
    ]
    assert api.motis.calls[0][1]["one"] == "46.948,7.439"


def test_a_trip_lists_its_stops(api):
    answer = api.get("/v2/map/trip", params={"id": "20261005_08:00_ch_t1"}).json()
    assert answer["name"] == "IC 5"
    assert [s["name"] for s in answer["stops"]] == ["Alpha", "Beta"]
    assert answer["polyline"] == "xyz"


def test_station_ids_are_those_of_v1():
    assert tmap._station_id("ch_Parentch:1:sloid:3000") == "8503000"
    assert tmap._station_id("ch_ch:1:sloid:2119:3:2") == "8502119"
    assert tmap._station_id("ch_8500002:0:1") == "8500002"
    assert tmap._station_id(None) is None


def test_a_point_that_is_no_coordinate_is_refused(api):
    response = api.get("/v2/map/vehicles", params={"min": "Bern", "max": "47.05,7.50"})
    assert response.status_code == 400
    assert "latitude,longitude" in response.json()["errors"][0]["message"]


def test_the_stations_are_the_busiest_first(api, monkeypatch):
    async def fetch(pool, query, *args):
        return [
            {
                "id": "8507000",
                "name": "Bern",
                "lat": 46.9488321,
                "lon": 7.4391,
                "mode": "train",
                "departures": 1200,
            }
        ]

    monkeypatch.setattr(tmap.db, "fetch", fetch)
    response = api.get("/v2/map/stations")
    assert response.json()["stations"] == [["8507000", "Bern", 46.948832, 7.4391, "train", 1200]]
    assert "max-age" in response.headers["cache-control"]


class Unreachable(FakeMotis):
    """Nothing on foot from the point asked for; everything from a station."""

    async def get(self, path, params):
        if path == "/api/v6/one-to-all" and params["one"] != "ch_station":
            self.calls.append((path, params))
            return {"all": []}
        answer = await super().get(path, params)
        # A place the router cannot name, and one without a time: both left out.
        answer["all"] += [{"place": {}, "duration": 3}, {"place": {"name": "X"}}]
        return answer


def test_reachable_starts_at_the_nearest_station_when_nothing_is_on_foot(api, monkeypatch):
    motis = Unreachable()
    api.app.dependency_overrides[tmap.get_motis] = lambda: motis

    async def fetch(pool, query, *args):
        return [{"id": "8507000", "name": "Bern", "lat": 46.9488, "lon": 7.4391}]

    async def router_place(pool, start):
        return "ch_station"

    monkeypatch.setattr(tmap.db, "fetch", fetch)
    monkeypatch.setattr(tmap, "router_place", router_place)
    answer = api.get(
        "/v2/map/reachable", params={"x": 47.2, "y": 7.2, "time": "2026-10-05T08:00:00Z"}
    ).json()

    assert answer["from"] == {"lat": 46.9488, "lon": 7.4391, "id": "8507000", "name": "Bern"}
    assert [s["id"] for s in answer["stops"]] == ["8500002"]
    assert motis.calls[0][1]["time"] == "2026-10-05T08:00:00Z"


def test_an_unknown_trip_is_a_404(api):
    class NoTrip(FakeMotis):
        async def get(self, path, params):
            return {"legs": []}

    api.app.dependency_overrides[tmap.get_motis] = lambda: NoTrip()
    response = api.get("/v2/map/trip", params={"id": "nothing"})
    assert response.status_code == 404


def test_a_delay_needs_both_times():
    assert tmap._delay(None, "2026-10-05T06:00:00Z") is None
    assert tmap._delay("2026-10-05T06:00:00Z", "2026-10-05T06:03:30Z") == 3


def test_the_cache_drops_what_has_expired_once_it_is_full(monkeypatch):
    import asyncio

    tmap._cache.clear()
    for index in range(2001):
        tmap._cache[("old", index)] = (0.0, index)

    async def produce():
        return "fresh"

    assert asyncio.run(tmap._cached(("new",), 60, produce)) == "fresh"
    assert list(tmap._cache) == [("new",)]
