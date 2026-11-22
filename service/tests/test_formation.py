"""Train formations: the short string, the plan of fetches, /v1/formation.

The strings are answers of the formation service of 22 November 2026.
"""

import asyncio
import os
from datetime import date, datetime, timedelta

import asyncpg
import httpx
import pytest
from fastapi.testclient import TestClient
from gtfs_feed import TODAY, write_feed

from transport_api import settings
from transport_api.main import app
from transport_api.mapping import ZURICH
from transport_api.models import FormationResponse
from transport_api.timetable import formation, formation_fetch, importer

# IC 1 at a station with sectors: fillers, a restaurant, a family car last.
IC = (
    "@A,F,F,F,F@B,[(FA:8#VH;NF,>2:7#NF,2:6#NF@C,2:5#NF,%W2:4#NF,1:3#NF,1:2#NF"
    "@D,1:1#BHP;BZ;NF,LK)],F,F,F,F"
)


def test_the_train_is_read_front_first_without_fillers():
    cars = formation.coaches(IC)
    assert [c["position"] for c in cars] == list(range(1, 10))
    assert [c["number"] for c in cars] == ["8", "7", "6", "5", "4", "3", "2", "1", None]
    assert [c["sector"] for c in cars] == ["B", "B", "B", "C", "C", "C", "C", "D", "D"]
    assert [c["type"] for c in cars] == [
        *("family", "coach", "coach", "coach", "restaurant", "coach", "coach", "coach"),
        "locomotive",
    ]
    assert [c["classes"] for c in cars] == [[2], [2], [2], [2], [2], [1], [1], [1], []]
    assert cars[0]["offers"] == ["bicycle", "lowFloor"]
    assert cars[7]["offers"] == ["wheelchair", "business", "lowFloor"]
    assert cars[1]["groupsBoarding"] and not cars[2]["groupsBoarding"]
    assert cars[4]["unattended"] and not cars[4]["closed"]


def test_passage_ends_where_a_unit_ends():
    cars = formation.coaches("[(2,2,12),(12#VH,D,2)#VH]")
    assert [c["noPassageAhead"] for c in cars] == [True, False, False, True, False, False]
    assert [c["noPassageBehind"] for c in cars] == [False, False, True, False, False, True]
    assert [c["type"] for c in cars][3:] == ["coach", "baggage", "coach"]
    assert cars[0]["sector"] is None
    assert cars[-1]["offers"] == ["bicycle"]


def test_closed_coaches_stay_in_the_train():
    cars = formation.coaches("@A,F,[(2:7,W1:3#BHP@D,1):1@E,-(2,-2@F,-W1,-1)],F")
    assert [c["closed"] for c in cars] == [False, False, False, True, True, True, True]
    assert cars[2]["number"] == "1" and cars[1]["classes"] == [1]


def test_parked_coaches_are_not_the_train():
    cars = formation.coaches("@D,X,X,X,X,[(1:211#VH;NF@C,2:212#VH;NF,2):214]@A,F,F")
    assert [(c["number"], c["sector"]) for c in cars] == [("211", "D"), ("212", "C"), ("214", "C")]


@pytest.mark.parametrize("text", ["", None, "F,F", "[(2,what?,2)]", "[(2,2"])
def test_what_cannot_be_read_is_no_formation(text):
    assert formation.coaches(text) == []


DAY = date(2026, 11, 23)


def at(hour, minute=0, day=DAY):
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=ZURICH)


NOON, HALF_PAST_ONE = at(12), at(13, 30)


def train(start=NOON, end=HALF_PAST_ONE, refreshed=True, operation=DAY):
    return formation_fetch.Train(DAY, "SBB", "707", operation, start, end, refreshed)


def asked(when, found=True):
    return formation_fetch.State(asked_at=when, found=found, wanted=False)


WANTED = formation_fetch.State(asked_at=None, found=False, wanted=True)


@pytest.mark.parametrize(
    ("which", "state", "now", "reason"),
    [
        (train(), None, at(8, 59), None),
        (train(), None, at(9), "base"),
        (train(), None, at(12, 30), "base"),  # after a restart
        (train(), None, at(13, 31), None),
        (train(), WANTED, at(2, 30), "early"),
        (train(), WANTED, at(1, 30), None),  # no data that far ahead
        (train(), asked(at(2, 30)), at(5), None),
        (train(), asked(at(2, 30)), at(9), "base"),
        (train(), asked(at(9)), at(11, 39), None),
        (train(), asked(at(9)), at(11, 40), "refresh"),
        (train(refreshed=False), asked(at(9)), at(11, 40), None),
        (train(), asked(at(11, 40)), at(12, 45), "halfway"),
        (train(end=at(12, 50)), asked(at(11, 40)), at(12, 45), None),
        (train(refreshed=False), asked(at(9), found=False), at(11), "retry"),
        (train(refreshed=False), asked(at(11), found=False), at(11, 30), None),
        (train(start=at(1), end=at(2)), None, at(23, 30, DAY - timedelta(days=1)), None),
        (train(start=at(1), end=at(2)), None, at(0), "base"),
        (train(), asked(at(9)), at(0, 10, DAY + timedelta(days=1)), None),
    ],
)
def test_when_a_train_is_asked_for(which, state, now, reason):
    due = formation_fetch.due(which, state, now)
    assert (due[1] if due else None) == reason


def test_the_operation_day_of_a_train_of_the_next_morning():
    assert formation_fetch.operation_day(DAY, 24 * 3600 + 600) == DAY
    assert formation_fetch.operation_day(DAY, 30 * 3600) == DAY + timedelta(days=1)


def test_the_budget_holds():
    Used = formation_fetch.Used
    allowed = formation_fetch.allowed
    assert allowed("base", Used(total=18999), 19000)
    assert not allowed("base", Used(total=19000), 19000)
    # The last thousand is for trains not asked yet.
    assert not allowed("refresh", Used(total=18000), 19000)
    assert not allowed("early", Used(total=10, early=2000), 19000)
    assert not allowed("retry", Used(total=10, retry=1500), 19000)
    # A small budget, as on staging, still works.
    assert allowed("refresh", Used(total=10), 500)


DATABASE = os.environ.get("TEST_DATABASE_URL")
needs_database = pytest.mark.skipif(not DATABASE, reason="TEST_DATABASE_URL is not set")


def answer(day=TODAY, text="[(1:1,2:2)]"):
    def stop(uic, name, arrival, departure, track):
        return {
            "formationShort": {
                "formationShortString": text,
                "vehicleGoals": [
                    {
                        "fromVehicleAtPosition": 1,
                        "toVehicleAtPosition": 2,
                        "destinationStopPoint": {"uic": 8500003, "name": "Gamma, Dorf"},
                    }
                ],
            },
            "scheduledStop": {
                "stopPoint": {"uic": uic, "name": name},
                "stopTime": {
                    "arrivalTime": arrival and f"{day}T{arrival}:00+02:00",
                    "departureTime": departure and f"{day}T{departure}:00+02:00",
                },
                "track": track,
            },
        }

    return {
        "formationsAtScheduledStops": [
            stop(8500001, "Alpha", None, "08:00", "1"),
            stop(8500002, "Beta", "08:10", "08:12", "3"),
            stop(8500003, "Gamma, Dorf", "08:30", None, None),
        ]
    }


def run(work):
    async def with_connection():
        connection = await asyncpg.connect(DATABASE)
        try:
            return await work(connection)
        finally:
            await connection.close()

    return asyncio.run(with_connection())


@pytest.fixture(scope="module")
def loaded(tmp_path_factory):
    if not DATABASE:
        pytest.skip("TEST_DATABASE_URL is not set")
    path = write_feed(tmp_path_factory.mktemp("gtfs"))
    run(lambda connection: importer.load(connection, path, TODAY, 14))


@pytest.fixture
def api(loaded, monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL", DATABASE)
    monkeypatch.setattr(formation, "OPERATORS", {"Test Bahn": "TEST"})
    monkeypatch.setattr(formation, "now", lambda: at(7, 0, TODAY))
    run(lambda c: c.execute("TRUNCATE rt.formation, rt.formation_call"))
    with TestClient(app) as client:
        yield client


def morning(stops=None):
    the_train = formation_fetch.Train(
        TODAY, "Test Bahn", "1234", TODAY, at(8, 0, TODAY), at(8, 30, TODAY), False
    )
    return run(lambda c: formation_fetch.store(c, the_train, "base", 200, stops, at(6, 0, TODAY)))


def get(api, trip="t-morning", day=TODAY):
    response = api.get("/v1/formation", params={"id": trip, "date": str(day)})
    assert response.status_code == 200
    FormationResponse.model_validate(response.json())
    return response.json()


@needs_database
def test_a_stored_formation_is_given_at_each_stop(api):
    morning(formation_fetch.compact(answer()))
    got = get(api)
    assert got["status"] == "available"
    assert [s["station"]["id"] for s in got["stops"]] == ["8500001", "8500002", "8500003"]
    first = got["stops"][0]
    assert first["departure"] == "2026-10-05T08:00:00+0200"
    assert first["platform"] == "1"
    assert [c["classes"] for c in first["coaches"]] == [[1], [2]]
    assert first["destinations"] == [
        {"id": "8500003", "name": "Gamma, Dorf", "fromPosition": 1, "toPosition": 2}
    ]


@needs_database
def test_the_formation_of_another_run_of_the_number_is_not_shown(api):
    morning(formation_fetch.compact(answer(day=TODAY - timedelta(days=1))))
    got = get(api)
    assert got["status"] == "none"
    assert got["stops"] == []


@needs_database
def test_before_it_is_fetched_it_is_pending_and_asked_for(api, monkeypatch):
    monkeypatch.setattr(formation, "now", lambda: at(4, 0, TODAY))
    got = get(api)
    assert got["status"] == "pending"
    assert got["availableFrom"] == "2026-10-05T05:00:00+0200"
    rows = run(lambda c: c.fetch("SELECT wanted, asked_at FROM rt.formation"))
    assert [(r["wanted"], r["asked_at"]) for r in rows] == [(True, None)]


@needs_database
def test_without_a_formation_there_is_none(api):
    morning(None)
    assert get(api)["status"] == "none"


@needs_database
def test_other_trips(api, monkeypatch):
    assert get(api, "no-such-trip")["status"] == "unknown"
    monkeypatch.setattr(formation, "OPERATORS", {})
    assert get(api)["status"] == "unsupported"
    assert api.get("/v1/formation").status_code == 400
    assert api.get("/v1/formation?id=x&date=soon").status_code == 400


@needs_database
def test_a_failure_keeps_what_was_known_and_a_change_is_noted(api):
    morning(formation_fetch.compact(answer()))
    morning(None)
    assert get(api)["status"] == "available"
    morning(formation_fetch.compact(answer(text="[(2:2,1:1)]")))
    changed = run(lambda c: c.fetch("SELECT changed FROM rt.formation_call ORDER BY id"))
    assert [r["changed"] for r in changed] == [None, None, True]


@needs_database
def test_the_days_trains_are_planned_and_fetched(api, monkeypatch):
    monkeypatch.setattr(settings, "OTD_FORMATION_KEY", "secret")
    seen = []

    def handler(request):
        seen.append(request)
        return httpx.Response(200, json=answer())

    async def work(connection):
        now = at(7, 0, TODAY)
        trains = await formation_fetch.load_trains(connection, TODAY)
        queue = await formation_fetch.planned(connection, trains, now, 19000)
        assert [(t.number, r) for t, r in queue] == [("1234", "base")]
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            await formation_fetch.fetch_one(client, connection, *queue[0], now)
        assert await formation_fetch.planned(connection, trains, now, 19000) == []

    run(work)
    assert dict(seen[0].url.params) == {
        "evu": "TEST",
        "operationDate": str(TODAY),
        "trainNumber": "1234",
    }
    assert seen[0].headers["authorization"] == "Bearer secret"
    assert get(api)["status"] == "available"


@needs_database
@pytest.mark.parametrize(("status", "pause"), [(429, 60), (403, 600), (503, 10), (400, 0)])
def test_the_services_refusals(api, status, pause):
    the_train = formation_fetch.Train(
        TODAY, "Test Bahn", "1234", TODAY, at(8, 0, TODAY), at(8, 30, TODAY), False
    )
    transport = httpx.MockTransport(lambda request: httpx.Response(status, json={"error": "no"}))

    async def work(connection):
        async with httpx.AsyncClient(transport=transport) as client:
            return await formation_fetch.fetch_one(
                client, connection, the_train, "base", at(6, 0, TODAY)
            )

    assert run(work) == pause
    tried = run(lambda c: c.fetchval("SELECT count(*) FROM rt.formation"))
    # Refused for our sake, the train is asked for again; otherwise it was tried.
    assert tried == (0 if status in (403, 429) else 1)


def test_without_a_key_nothing_is_fetched(monkeypatch):
    monkeypatch.setattr(settings, "OTD_FORMATION_KEY", None)

    async def connect():
        raise AssertionError("connected without a key")

    asyncio.run(formation_fetch.keep_current(connect))


@needs_database
def test_one_turn_of_the_loop(api, monkeypatch):
    monkeypatch.setattr(settings, "OTD_FORMATION_KEY", "secret")
    turns = []

    async def fetched(*args):
        turns.append(args[2].number)
        return 0

    async def trains(connection, today):
        now = datetime.now(ZURICH)
        soon, later = now + timedelta(minutes=10), now + timedelta(hours=1)
        return [formation_fetch.Train(today, "Test Bahn", "1234", today, soon, later, False)]

    class Done(Exception):
        pass

    async def stop(seconds):
        raise Done

    async def work(connection):
        async def connect():
            return connection

        monkeypatch.setattr(formation_fetch.asyncio, "sleep", stop)
        with pytest.raises(Done):
            await formation_fetch.keep_current(connect)

    monkeypatch.setattr(formation_fetch, "load_trains", trains)
    monkeypatch.setattr(formation_fetch, "fetch_one", fetched)
    run(work)
    assert turns == ["1234"]
