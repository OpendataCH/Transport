"""The 30-second memory of repeated answers."""

import fakeredis
import pytest
from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.testclient import TestClient

from transport_api import response_cache, settings


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


def test_v1_from_search_ch_is_not_kept(api, monkeypatch):
    monkeypatch.setattr(settings, "V1_FROM_TIMETABLE", False)
    api.get("/v1/stationboard?station=Bern")
    api.get("/v1/stationboard?station=Bern")
    assert api.calls["n"] == 2
