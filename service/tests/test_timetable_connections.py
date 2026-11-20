"""Connections: MOTIS answers in, /v1's shape out.

The router is replaced by a recorded answer on the small test feed; the
stations and trips it names are looked up in a real Postgres, so these tests
need TEST_DATABASE_URL like test_timetable_db.py. The helpers at the top
need nothing.
"""

import asyncio
import os
from contextlib import asynccontextmanager
from datetime import date, datetime

import asyncpg
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from gtfs_feed import TODAY, write_feed

from transport_api import errors
from transport_api.mapping import ZURICH
from transport_api.models import ConnectionsResponse
from transport_api.timetable import connections, importer, places


def test_trip_id_drops_day_time_and_dataset():
    assert (
        connections._trip_id("20261006_07:59_ch_.ojp-91-81-A.1.TA.658.j26")
        == ".ojp-91-81-A.1.TA.658.j26"
    )
    assert connections._trip_id("plain") == "plain"


@pytest.mark.parametrize(
    ("category", "route", "product"),
    [
        ("IC", "IC5", "IC 5"),
        ("IR", "IR13", "IR 13"),
        ("ICE", "ICE", "ICE"),
        ("R", "R61", "R"),
        ("S", "S29", "S29"),
        ("RE", "RE37", "RE37"),
        ("B", "21", "21"),
        ("T", "9", "9"),
        (None, "X1", "X1"),
    ],
)
def test_products_are_named_as_search_ch_names_them(category, route, product):
    assert connections._product({"category": category, "route_short_name": route}) == product


def test_a_trip_only_real_time_knows_gets_its_category_from_the_line():
    trip = connections._trip_of_leg(
        {"routeShortName": "IC81", "tripShortName": "10818", "agencyName": "SBB"}
    )
    assert trip["category"] == "IC"
    assert connections._product(trip) == "IC 81"


def test_delay_cuts_the_seconds():
    assert connections._delay("2026-10-05T06:02:59Z", "2026-10-05T06:00:00Z") == 2
    assert connections._delay("2026-10-05T06:00:00Z", "2026-10-05T06:00:00Z") == 0


def test_modes_translate_to_motis():
    assert connections._modes(["bus", "ship"]) == ["BUS", "COACH", "FERRY"]
    assert connections._modes(["all"]) is None


def trip(start, end):
    return {"startTime": f"2026-10-05T{start}:00Z", "endTime": f"2026-10-05T{end}:00Z"}


class PagingMotis:
    """Arrivals before 09:00 first, then two later windows behind a cursor."""

    def __init__(self) -> None:
        self.calls = []

    async def plan(self, params):
        self.calls.append(params)
        windows = {
            None: [trip("05:00", "06:30"), trip("06:00", "07:30"), trip("07:00", "08:30")],
            "next-1": [trip("07:30", "09:10"), trip("08:00", "09:40")],
            "next-2": [trip("08:30", "10:10"), trip("09:00", "10:40")],
        }
        cursor = params.get("pageCursor")
        following = {None: "next-1", "next-1": "next-2", "next-2": None}[cursor]
        return {"itineraries": windows[cursor], "nextPageCursor": following}


@pytest.mark.parametrize(
    ("page", "expected"),
    [(0, ["07:30", "08:30"]), (1, ["09:10", "09:40"]), (2, ["10:10", "10:40"])],
)
def test_arrival_pages_are_cut_as_v1_cuts_them(page, expected):
    """Page 0 arrives last before the time, page 1 is the next ones after it."""
    motis = PagingMotis()
    got = asyncio.run(connections._arrival_page(motis, {"arriveBy": "true"}, 2, page))
    assert [i["endTime"][11:16] for i in got] == expected


DATABASE = os.environ.get("TEST_DATABASE_URL")
needs_database = pytest.mark.skipif(not DATABASE, reason="TEST_DATABASE_URL is not set")


def place(stop_id, parent, name, at, *, track=None, actual=None, kind="departure"):
    when = {f"scheduled{kind.capitalize()}": at, kind: actual or at}
    return {
        "name": name,
        "stopId": stop_id,
        **({"parentId": parent} if parent else {}),
        "lat": 46.9,
        "lon": 7.4,
        **when,
        **({"track": track, "scheduledTrack": track} if track else {}),
    }


# 08:00 from Alpha on the S1 (two minutes late), a platform change at Beta,
# then an extra RE that only real time knows to Gamma.
PLAN = {
    "itineraries": [
        {
            "startTime": "2026-10-05T06:00:00Z",
            "endTime": "2026-10-05T06:30:00Z",
            "duration": 1800,
            "transfers": 1,
            "legs": [
                {
                    "mode": "SUBURBAN",
                    "realTime": True,
                    "tripId": "20261005_08:00_ch_t-morning",
                    "routeShortName": "S1",
                    "tripShortName": "1234",
                    "headsign": "Gamma, Dorf",
                    "agencyName": "Test Bahn",
                    "duration": 600,
                    "from": place(
                        "ch_ch:1:sloid:1:1:1",
                        "ch_ch:1:sloid:1",
                        "Alpha",
                        "2026-10-05T06:00:00Z",
                        track="1",
                        actual="2026-10-05T06:02:30Z",
                    ),
                    "to": place(
                        "ch_ch:1:sloid:2:0:1",
                        "ch_ch:1:sloid:2",
                        "Beta",
                        "2026-10-05T06:10:00Z",
                        track="3",
                        actual="2026-10-05T06:12:00Z",
                        kind="arrival",
                    ),
                    "intermediateStops": [],
                },
                {
                    "mode": "WALK",
                    "duration": 240,
                    "from": place("ch_ch:1:sloid:2:0:1", "ch_ch:1:sloid:2", "Beta", "x"),
                    "to": place("ch_ch:1:sloid:2:0:1", "ch_ch:1:sloid:2", "Beta", "x"),
                },
                {
                    "mode": "REGIONAL_RAIL",
                    "realTime": False,
                    "tripId": "20261005_08:20_ch_ojp:extra_20261005",
                    "routeShortName": "RE37",
                    "tripShortName": "4815",
                    "headsign": "Gamma, Dorf",
                    "agencyName": "Extra Bahn",
                    "duration": 600,
                    "from": place(
                        "ch_ch:1:sloid:2:0:1",
                        "ch_ch:1:sloid:2",
                        "Beta",
                        "2026-10-05T06:20:00Z",
                        track="3",
                    ),
                    "to": place(
                        "ch_8500003", None, "Gamma, Dorf", "2026-10-05T06:30:00Z", kind="arrival"
                    ),
                    "intermediateStops": [],
                },
            ],
        }
    ]
}


GEOCODE = [
    {
        "type": "ADDRESS",
        "name": "Neufeldstrasse 101",
        "street": "Neufeldstrasse",
        "houseNumber": "101",
        "lat": 46.957123,
        "lon": 7.434012,
        "areas": [{"name": "Schweiz", "adminLevel": 2}, {"name": "Bern", "adminLevel": 8.0}],
    }
]

REVERSE_GEOCODE = [
    {
        "type": "ADDRESS",
        "street": "Neufeldstrasse",
        "houseNumber": "101",
        "zip": "3012",
        "lat": 46.957123,
        "lon": 7.434012,
        "areas": [{"name": "Bern", "adminLevel": 8.0}],
    }
]


class FakeMotis:
    def __init__(self) -> None:
        self.params: dict | None = None

    async def plan(self, params):
        self.params = params
        return PLAN

    async def get(self, path, params):
        if path == "/api/v1/reverse-geocode":
            return REVERSE_GEOCODE if params["place"].startswith("46.9") else []
        assert path == "/api/v1/geocode"
        return GEOCODE if "Neufeld" in params["text"] else []


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    path = write_feed(tmp_path_factory.mktemp("gtfs"))

    async def load():
        connection = await asyncpg.connect(DATABASE)
        try:
            await importer.load(connection, path, TODAY, 14)
        finally:
            await connection.close()

    asyncio.run(load())


@pytest.fixture
def api(loaded):
    motis = FakeMotis()

    @asynccontextmanager
    async def lifespan(app):
        app.state.timetable = await asyncpg.create_pool(DATABASE, min_size=0, max_size=2)
        yield
        await app.state.timetable.close()

    app = FastAPI(lifespan=lifespan)
    errors.install(app)
    app.include_router(connections.router, prefix="/v2")
    app.dependency_overrides[connections.get_motis] = lambda: motis
    with TestClient(app) as client:
        client.motis = motis
        yield client


@needs_database
def test_a_connection_in_the_shape_of_v1(api):
    answer = api.get(
        "/v2/connections", params={"from": "Alpha", "to": "8500003", "datetime": f"{TODAY} 07:55"}
    ).json()
    ConnectionsResponse.model_validate(answer)

    assert api.motis.params["fromPlace"] == "ch_ch:1:sloid:1"
    assert api.motis.params["toPlace"] == "ch_8500003"
    assert api.motis.params["directModes"] == ""
    # About 5 km/h to the first stop, as journey planners walk.
    assert api.motis.params["pedestrianSpeed"] == "1.4"

    assert answer["from"]["id"] == "8500001"
    assert answer["stations"]["to"][0]["name"] == "Gamma, Dorf"
    connection = answer["connections"][0]
    assert connection["duration"] == "00d00:30:00"
    assert connection["transfers"] == 1
    assert connection["products"] == ["S1", "RE37"]
    # The walk between two platforms of Beta is no section of its own.
    assert [s["journey"]["name"] for s in connection["sections"]] == ["001234", "004815"]

    departure = connection["from"]
    assert departure["station"]["id"] == "8500001"
    assert departure["departure"] == "2026-10-05T08:00:00+0200"
    assert departure["platform"] == "1"
    assert departure["delay"] == 2
    assert departure["prognosis"]["departure"] == "2026-10-05T08:02:00+0200"

    arrival = connection["to"]
    assert arrival["arrival"] == "2026-10-05T08:30:00+0200"
    assert arrival["platform"] == ""  # none known: /v1's empty string
    assert arrival["delay"] is None  # no real time on that leg

    first, second = connection["sections"]
    assert first["journey"]["category"] == "S"
    assert first["journey"]["operator"] == "Test Bahn"
    assert second["journey"]["category"] == "RE"
    assert second["journey"]["operator"] == "Extra Bahn"


@needs_database
def test_more_than_two_via_stops_are_refused(api):
    response = api.get(
        "/v2/connections",
        params=[("from", "Alpha"), ("to", "Beta")] + [("via[]", "Gamma, Dorf")] * 3,
    )
    assert response.status_code == 400
    assert "max 2" in response.json()["errors"][0]


@needs_database
def test_unknown_places_give_the_empty_answer(api):
    answer = api.get("/v2/connections", params={"from": "nowhere-xyz", "to": "Beta"}).json()
    assert answer == {
        "connections": [],
        "from": None,
        "to": None,
        "stations": {"from": [], "to": []},
    }
    assert api.motis.params is None


@needs_database
def test_with_a_via_stop_v1_names_it_as_to(api):
    answer = api.get(
        "/v2/connections",
        params={"from": "Alpha", "to": "8500003", "via[]": "Beta", "datetime": f"{TODAY} 07:55"},
    ).json()
    assert api.motis.params["via"] == "ch_ch:1:sloid:2"
    assert answer["to"]["name"] == "Beta"
    assert answer["stations"]["to"][0]["name"] == "Beta"


def test_a_walk_between_stations_is_its_seconds():
    leg = {
        "mode": "WALK",
        "duration": 180,
        "from": {"stopId": "ch_a", "parentId": "ch_A", "name": "A"},
        "to": {"stopId": "ch_b", "parentId": "ch_B", "name": "B"},
    }
    section = connections._section(leg, {}, {}, {}, None)
    assert section["walk"] == {"duration": 180}


def test_a_train_leaves_each_station_as_full_as_forecast():
    def place(stop_id, at):
        return {
            "stopId": f"ch_{stop_id}",
            "name": stop_id,
            "scheduledDeparture": at,
            "scheduledArrival": at,
        }

    leg = {
        "mode": "HIGHSPEED_RAIL",
        "tripId": "20261120_05:25_ch_.ojp-91-1-D",
        "from": place("bern", "2026-11-20T06:31:00Z"),
        "intermediateStops": [place("olten", "2026-11-20T06:58:00Z")],
        "to": place("zurich", "2026-11-20T07:28:00Z"),
    }
    stations = {
        "bern": {"id": "8507000", "name": "Bern", "lat": None, "lon": None},
        "olten": {"id": "8500218", "name": "Olten", "lat": None, "lon": None},
        "zurich": {"id": "8503000", "name": "Zürich HB", "lat": None, "lon": None},
    }
    trips = {
        ".ojp-91-1-D": {
            "short_name": "707",
            "route_short_name": "IC1",
            "category": "IC",
            "operator": "SBB",
            "headsign": "St. Gallen",
            "mode": "train",
        }
    }
    # Full in second class from Olten; nothing known at Zürich, where it is left.
    forecast = {(date(2026, 11, 20), "707"): {8507000: (1, 2), 8500218: (1, 3), 8503000: (2, 2)}}
    now = datetime(2026, 11, 20, 7, 0, tzinfo=ZURICH)
    section = connections._section(leg, stations, trips, forecast, now)
    stops = section["journey"]["passList"]
    assert [(s["prognosis"]["capacity1st"], s["prognosis"]["capacity2nd"]) for s in stops] == [
        (1, 2),
        (1, 3),
        (None, None),
    ]
    assert (section["journey"]["capacity1st"], section["journey"]["capacity2nd"]) == (1, 3)

    # A bus with the same number is not the train.
    trips[".ojp-91-1-D"]["mode"] = "bus"
    bus = connections._section(leg, stations, trips, forecast, now)
    assert bus["journey"]["capacity2nd"] is None


@needs_database
def test_a_connection_from_an_address_starts_at_its_coordinate(api):
    answer = api.get(
        "/v2/connections",
        params={"from": "Neufeldstrasse 101, Bern", "to": "8500003", "datetime": f"{TODAY} 07:55"},
    ).json()
    assert api.motis.params["fromPlace"] == "46.957123,7.434012"
    assert answer["from"]["id"] is None
    assert answer["from"]["name"] == "Bern, Neufeldstrasse 101"
    assert answer["from"]["coordinate"]["x"] == 46.957123


@needs_database
def test_a_connection_from_a_coordinate_starts_at_that_point(api):
    answer = api.get(
        "/v2/connections",
        params={"from": "46.9572,7.4341", "to": "8500003", "datetime": f"{TODAY} 07:55"},
    ).json()
    # The point asked for, not the address that names it.
    assert api.motis.params["fromPlace"] == "46.9572,7.4341"
    assert answer["from"]["id"] is None
    assert answer["from"]["name"] == "Neufeldstrasse 101, 3012 Bern"
    assert answer["from"]["coordinate"]["x"] == 46.9572
    assert answer["connections"]


@needs_database
def test_a_coordinate_without_an_address_nearby_is_its_own_name(api):
    answer = api.get(
        "/v2/connections",
        params={"from": "Alpha", "to": "47.5, 8.25", "datetime": f"{TODAY} 07:55"},
    ).json()
    assert api.motis.params["toPlace"] == "47.5,8.25"
    assert answer["to"]["name"] == "47.5,8.25"


@needs_database
def test_an_address_too_far_off_does_not_name_a_coordinate(api):
    # About 330 metres north of Neufeldstrasse 101.
    answer = api.get(
        "/v2/connections",
        params={"from": "46.96,7.4341", "to": "8500003", "datetime": f"{TODAY} 07:55"},
    ).json()
    assert api.motis.params["fromPlace"] == "46.96,7.4341"
    assert answer["from"]["name"] == "46.96,7.4341"


def test_only_a_bare_coordinate_is_a_point():
    assert places.point("47.3769,8.5417") == (47.3769, 8.5417)
    assert places.point(" 46.95 , 7.43 ") == (46.95, 7.43)
    assert places.point("Bern") is None
    assert places.point("8507000") is None
    assert places.point("Weberstrasse 9, Aarburg") is None
    assert places.point("91.0,8.5") is None


@needs_database
def test_shared_vehicles_only_when_asked_for(api, monkeypatch):
    import copy

    plain = api.get(
        "/v2/connections", params={"from": "Alpha", "to": "8500003", "datetime": f"{TODAY} 07:55"}
    ).json()
    assert "preTransitModes" not in api.motis.params
    assert all("rental" not in s for c in plain["connections"] for s in c["sections"])

    plan = copy.deepcopy(PLAN)
    walk = plan["itineraries"][0]["legs"][1]
    walk["mode"] = "RENTAL"
    walk["rental"] = {
        "systemName": "Lime City partners from Partners::RegionFeedMediator",
        "formFactor": "SCOOTER_STANDING",
        "propulsionType": "ELECTRIC",
        "rentalUriWeb": "https://example.org/lime",
    }
    walk["from"] = place("ch_ch:1:sloid:2:0:1", "ch_ch:1:sloid:2", "Beta", "2026-10-05T06:10:00Z")
    walk["to"] = place("ch_8500003", None, "Gamma, Dorf", "2026-10-05T06:14:00Z", kind="arrival")

    async def rental_plan(params):
        api.motis.params = params
        return plan

    monkeypatch.setattr(api.motis, "plan", rental_plan)
    answer = api.get(
        "/v2/connections",
        params={
            "from": "Alpha",
            "to": "8500003",
            "datetime": f"{TODAY} 07:55",
            "sharedMobility": "1",
        },
    ).json()
    ConnectionsResponse.model_validate(answer)
    assert api.motis.params["preTransitModes"] == "WALK,RENTAL"
    rental = next(s for s in answer["connections"][0]["sections"] if "rental" in s)
    assert rental["walk"]["duration"] == 240 and rental["journey"] is None
    assert rental["rental"] == {
        "provider": "Lime City partners",
        "vehicle": "scooter_standing",
        "propulsion": "electric",
        "from_station": None,
        "to_station": None,
        "url": "https://example.org/lime",
    }


def test_the_category_gives_the_product_class_as_hafas_numbered_it():
    from transport_api.timetable.mapping import category_code

    assert [category_code(c) for c in ("TGV", "IC", "IR", "RE", "S", "B", "T", "BAT", "FUN")] == [
        0,
        1,
        2,
        3,
        5,
        6,
        9,
        4,
        7,
    ]
    assert category_code(None) is None
    assert category_code("XYZ") is None
