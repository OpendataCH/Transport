"""The 30-second memory of repeated answers."""

from datetime import datetime

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from transport_api import response_cache, settings
from transport_api.mapping import ZURICH


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(settings, "V1_FROM_TIMETABLE", True)
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    calls = {"n": 0}
    app = FastAPI()

    @app.get("/v1/stationboard")
    def board(station: str):
        calls["n"] += 1
        return JSONResponse({"station": station, "n": calls["n"], "name": "Zürich"})

    @app.get("/v1/locations")
    def locations():
        calls["n"] += 1
        return {"n": calls["n"]}

    app.add_middleware(response_cache.ResponseCacheMiddleware, redis_of=lambda: redis)
    with TestClient(app) as client:
        client.calls = calls
        yield client


def test_a_repeated_board_comes_from_the_cache(api):
    first = api.get("/v1/stationboard?station=Bern&limit=5").json()
    again = api.get("/v1/stationboard?limit=5&station=Bern").json()
    assert first == again and api.calls["n"] == 1
    assert again["name"] == "Zürich"


def test_other_parameters_and_endpoints_are_asked_anew(api):
    api.get("/v1/stationboard?station=Bern")
    api.get("/v1/stationboard?station=Basel")
    api.get("/v1/locations")
    api.get("/v1/locations")
    assert api.calls["n"] == 4


@pytest.mark.parametrize(
    ("path", "query", "seconds"),
    [
        ("/v1/connections", b"from=Bern&to=Thun", 100),
        ("/v1/connections", b"from=Bern&to=Thun&time=", 100),
        ("/v1/connections", b"from=Bern&to=Thun&time=08:00", 30),
        ("/v1/connections", b"from=Bern&to=Thun&date=2026-10-06", 30),
        ("/v1/stationboard", b"station=Bern", 30),
    ],
)
def test_connections_from_now_are_kept_longer(path, query, seconds, monkeypatch):
    monkeypatch.setattr(settings, "CONNECTIONS_NOW_CACHE_SECONDS", 100)
    assert response_cache.seconds_kept(path, query) == seconds


NOW = datetime(2026, 10, 5, 14, 13, 30, tzinfo=ZURICH)


@pytest.mark.parametrize(
    ("query", "now"),
    [
        (b"from=Bern&to=Thun&date=2026-10-05&time=14:13:36.806931", True),
        (b"from=Bern&to=Thun&time=14:12", True),
        (b"from=Bern&to=Thun&date=2026-10-05&time=14:20", False),
        (b"from=Bern&to=Thun&date=2026-10-06&time=14:13", False),
        (b"from=Bern&to=Thun&date=2026-10-05", False),
        (b"from=Bern&to=Thun&time=nonsense", False),
    ],
)
def test_a_time_close_to_now_counts_as_now(query, now):
    key = response_cache.cache_key("/v1/connections", query, NOW)
    assert (key == response_cache.cache_key("/v1/connections", b"to=Thun&from=Bern")) is now
    kept = response_cache.seconds_kept("/v1/connections", query, NOW)
    assert (kept == settings.CONNECTIONS_NOW_CACHE_SECONDS) is now


def test_v1_from_search_ch_is_not_kept(api, monkeypatch):
    monkeypatch.setattr(settings, "V1_FROM_TIMETABLE", False)
    api.get("/v1/stationboard?station=Bern")
    api.get("/v1/stationboard?station=Bern")
    assert api.calls["n"] == 2
