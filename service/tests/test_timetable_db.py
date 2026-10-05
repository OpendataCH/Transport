"""/v2/locations and /v2/stationboard against a real Postgres.

Skipped unless TEST_DATABASE_URL names a database the test may overwrite,
for example the development one:

    TEST_DATABASE_URL=postgresql://transport:transport@localhost:5434/transport_test pytest

The schemas `gtfs`, `gtfs_next` and `rt` in it are replaced.
"""

import asyncio
import os
from datetime import timedelta

import asyncpg
import pytest
from fastapi.testclient import TestClient
from gtfs_feed import TODAY, write_feed

from transport_api import settings
from transport_api.main import app
from transport_api.models import LocationsResponse, StationBoardResponse
from transport_api.timetable import importer

DATABASE = os.environ.get("TEST_DATABASE_URL")

pytestmark = pytest.mark.skipif(not DATABASE, reason="TEST_DATABASE_URL is not set")


def run(coroutine):
    return asyncio.run(coroutine)


async def _load(path, today=TODAY, days=14):
    connection = await asyncpg.connect(DATABASE)
    try:
        return await importer.load(connection, path, today, days)
    finally:
        await connection.close()


async def _sql(query, *args):
    connection = await asyncpg.connect(DATABASE)
    try:
        return await connection.fetch(query, *args)
    finally:
        await connection.close()


@pytest.fixture(scope="module")
def feed(tmp_path_factory):
    path = write_feed(tmp_path_factory.mktemp("gtfs"))
    run(_load(path))
    return path


@pytest.fixture
def api(feed, monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL", DATABASE)
    with TestClient(app) as client:
        yield client
    run(_sql("TRUNCATE rt.stop_delay, rt.trip_cancelled"))


def test_import_counts(feed):
    rows = run(_sql("SELECT count(*) AS n FROM gtfs.station"))
    assert rows[0]["n"] == 3
    trips = {r["trip_id"] for r in run(_sql("SELECT trip_id FROM gtfs.trips"))}
    # The headway template is replaced by its three runs.
    assert "t-headway" not in trips
    assert {"t-headway@32400", "t-headway@33000", "t-headway@33600"} <= trips


def test_a_failed_import_leaves_the_loaded_timetable(feed, tmp_path):
    broken = tmp_path / "broken.zip"
    broken.write_bytes(b"not a zip")
    with pytest.raises(Exception):  # noqa: B017 - any failure will do
        run(_load(broken))
    rows = run(_sql("SELECT count(*) AS n FROM gtfs.station"))
    assert rows[0]["n"] == 3


def test_locations_by_name(api):
    answer = api.get("/v2/locations", params={"query": "alpha"}).json()
    LocationsResponse.model_validate(answer)
    first = answer["stations"][0]
    assert first["id"] == "8500001"
    assert first["name"] == "Alpha"
    assert first["icon"] == "train"
    assert first["coordinate"] == {"type": "WGS84", "x": 46.9, "y": 7.4}


def test_locations_by_name_folds_accents_and_finds_words(api):
    answer = api.get("/v2/locations", params={"query": "dörf"}).json()
    assert [s["name"] for s in answer["stations"]] == ["Gamma, Dorf"]


def test_locations_by_coordinate_have_distances(api):
    answer = api.get("/v2/locations", params={"x": "47.0", "y": "7.5"}).json()
    assert answer["stations"][0]["name"] == "Beta"
    assert answer["stations"][0]["distance"] == 0
    assert isinstance(answer["stations"][1]["distance"], int)


def test_locations_without_a_question_are_empty(api):
    assert api.get("/v2/locations").json() == {"stations": []}


def _board(api, **params):
    answer = api.get("/v2/stationboard", params=params).json()
    StationBoardResponse.model_validate(answer)
    return answer


def test_board_by_id(api):
    answer = _board(api, id="8500001", limit="5", datetime=f"{TODAY} 07:00")
    assert answer["station"]["name"] == "Alpha"
    assert "icon" not in answer["station"]
    first = answer["stationboard"][0]
    assert first["stop"]["departure"] == "2026-10-05T08:00:00+0200"
    assert first["stop"]["platform"] == "1"
    assert first["name"] == "001234"
    assert first["category"] == "S"
    assert first["number"] == "1"
    assert first["to"] == "Gamma, Dorf"
    assert first["operator"] == "Test Bahn"
    # /v1: the stop's location and the head of the pass list carry only the
    # terminal's id.
    assert first["stop"]["location"]["id"] == "8500003"
    assert first["stop"]["location"]["name"] is None
    assert [s["station"]["id"] for s in first["passList"]] == ["8500003", "8500002", "8500003"]
    assert first["passList"][-1]["departure"] is None


def test_board_by_name_includes_the_headway_runs(api):
    answer = _board(api, station="Alpha", limit="10", datetime=f"{TODAY} 08:30")
    times = [j["stop"]["departure"][11:16] for j in answer["stationboard"]]
    assert times[:3] == ["09:00", "09:10", "09:20"]


def test_board_reaches_back_into_yesterdays_service_day(api):
    # t-night leaves at 24:10 on Monday's service day, i.e. Tuesday 00:10.
    tuesday = TODAY + timedelta(days=1)
    answer = _board(api, id="8500001", limit="1", datetime=f"{tuesday} 00:00")
    assert answer["stationboard"][0]["stop"]["departure"] == "2026-10-06T00:10:00+0200"
    assert answer["stationboard"][0]["name"] == "001299"


def test_board_reaches_into_tomorrows_service_day(api):
    # Nothing runs on Tuesday afternoon; the next departure is Wednesday's
    # first, on the next service day but within the board's horizon.
    tuesday = TODAY + timedelta(days=1)
    answer = _board(api, id="8500001", limit="1", datetime=f"{tuesday} 13:00")
    assert answer["stationboard"][0]["stop"]["departure"] == "2026-10-07T08:00:00+0200"


def test_board_skips_a_removed_day(api):
    tuesday = TODAY + timedelta(days=1)  # "daily" is removed on the 6th
    answer = _board(api, id="8500001", limit="3", datetime=f"{tuesday} 07:00")
    assert all(not j["stop"]["departure"].startswith("2026-10-06") for j in answer["stationboard"])


def test_board_does_not_depart_from_the_last_stop(api):
    answer = _board(api, id="8500003", limit="5", datetime=f"{TODAY} 07:00")
    assert answer["stationboard"] == []
    arrivals = _board(api, id="8500003", limit="5", type="arrival", datetime=f"{TODAY} 07:00")
    assert arrivals["stationboard"][0]["stop"]["departure"] == "2026-10-05T08:30:00+0200"


def test_board_filters_by_transportation(api):
    answer = _board(
        api, id="8500001", limit="5", datetime=f"{TODAY} 07:00", **{"transportations[]": "bus"}
    )
    assert {j["category"] for j in answer["stationboard"]} == {"B"}


def test_board_with_real_time(api):
    run(
        _sql(
            "INSERT INTO rt.stop_delay VALUES"
            " ('t-morning', $1, 1, NULL, 2), ('t-morning', $1, 2, 3, 3)",
            TODAY,
        )
    )
    answer = _board(api, id="8500001", limit="1", datetime=f"{TODAY} 07:00")
    journey = answer["stationboard"][0]
    assert journey["stop"]["delay"] == 2
    assert journey["stop"]["prognosis"]["departure"] == "2026-10-05T08:02:00+0200"
    assert journey["passList"][1]["delay"] == 3
    assert journey["passList"][1]["prognosis"]["arrival"] == "2026-10-05T08:13:00+0200"


def test_board_drops_a_cancelled_trip(api):
    run(_sql("INSERT INTO rt.trip_cancelled VALUES ('t-morning', $1)", TODAY))
    answer = _board(api, id="8500001", limit="1", datetime=f"{TODAY} 07:00")
    assert answer["stationboard"][0]["stop"]["departure"] != "2026-10-05T08:00:00+0200"


def test_board_without_a_stop_is_empty(api):
    assert _board(api) == {"station": None, "stationboard": []}


def test_v1_is_untouched(api, search_ch):
    search_ch.returns([])
    api.get("/v1/locations", params={"query": "Bern"})
    assert search_ch.requests, "/v1 still asks search.ch"


def test_a_delay_holds_until_the_next_report(api):
    # Reported at the first stop only; GTFS-RT means it to carry on.
    run(_sql("INSERT INTO rt.stop_delay VALUES ('t-morning', $1, 1, NULL, 4)", TODAY))
    answer = _board(api, id="8500001", limit="1", datetime=f"{TODAY} 07:00")
    beta, gamma = answer["stationboard"][0]["passList"][1:]
    assert beta["prognosis"]["arrival"] == "2026-10-05T08:14:00+0200"
    assert beta["prognosis"]["departure"] == "2026-10-05T08:16:00+0200"
    assert gamma["delay"] == 4


class _ReverseGeocoder:
    async def get(self, path, params):
        assert path == "/api/v1/reverse-geocode"
        return [
            {
                "type": "ADDRESS",
                "street": "Seftigenstrasse",
                "houseNumber": "4",
                "zip": "3007",
                "lat": 47.0001,
                "lon": 7.5001,
                "areas": [{"name": "Bern", "adminLevel": 8.0}],
            }
        ]


def test_locations_by_coordinate_name_the_nearest_address_first(api):
    from transport_api.timetable.router import motis_or_none

    app.dependency_overrides[motis_or_none] = lambda: _ReverseGeocoder()
    try:
        answer = api.get("/v2/locations", params={"x": "47.0", "y": "7.5"}).json()
    finally:
        app.dependency_overrides.pop(motis_or_none)
    LocationsResponse.model_validate(answer)
    first = answer["stations"][0]
    assert first["id"] is None
    assert first["name"] == "Seftigenstrasse 4, 3007 Bern"
    assert first["icon"] is None
    assert 10 < first["distance"] < 15 and not float(first["distance"]).is_integer()
    assert answer["stations"][1]["name"] == "Beta"
