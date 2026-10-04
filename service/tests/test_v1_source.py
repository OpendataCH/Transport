"""Which source answers /v1, switched by V1_FROM_TIMETABLE."""

from fastapi.testclient import TestClient

from transport_api import main, settings


def test_v1_asks_search_ch_by_default():
    assert main.from_search_ch("/v1")
    assert not main.from_search_ch("/v2")
    assert main.from_search_ch("/v1-old")


def test_v1_answers_from_the_timetable_when_switched(monkeypatch):
    monkeypatch.setattr(settings, "V1_FROM_TIMETABLE", True)
    assert not main.from_search_ch("/v1")
    assert not main.from_search_ch("/v2")
    assert main.from_search_ch("/v1-old")


def test_the_old_prefix_is_mounted():
    with TestClient(main.app) as client:
        assert client.get("/v1-old/").json()["version"] == "1.0"
