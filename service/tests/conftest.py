"""Test fixtures.

`timetable` stands in for the database and the router, for the tests that are
about what happens around an answer - headers, encoding, `fields[]`,
statistics - rather than about the timetable itself. The timetable is tested
against a real Postgres in test_timetable_db.py and
test_timetable_connections.py.
"""

import pytest
from fastapi.testclient import TestClient

from transport_api import errors
from transport_api.main import app
from transport_api.timetable import connections, db, locations, router, stationboard
from transport_api.timetable.mapping import location


class FakeTimetable:
    """The timetable, replaced by something that answers on command and remembers.

    `/locations?query=` gives the stations set with `returns`; a station board
    and a connection search find no stop and give their empty answers.
    `raises` makes every one of them fail instead.
    """

    def __init__(self) -> None:
        self.queries: list[str] = []
        self._stations: list[dict] = []
        self._error: errors.ApiError | None = None

    def returns(self, stations: list[dict]) -> None:
        self._stations = stations

    def raises(self, error: errors.ApiError) -> None:
        self._error = error

    async def by_query(self, pool, motis, query: str, kind: str) -> list[dict]:
        self.queries.append(query)
        self._fail()
        return self._stations

    async def station(self, pool, wanted: str):
        self.queries.append(wanted)
        self._fail()
        return None

    async def endpoint(self, pool, motis, text: str):
        self.queries.append(text)
        self._fail()
        return None

    def _fail(self) -> None:
        if self._error is not None:
            raise self._error


def station(id_: str | None, name: str, lat: float, lon: float, **extra) -> dict:
    """A location as /v1 writes it."""
    return location(id_, name, lat, lon, **extra)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def timetable(monkeypatch):
    fake = FakeTimetable()
    monkeypatch.setattr(locations, "_by_query", fake.by_query)
    monkeypatch.setattr(stationboard, "_station", fake.station)
    monkeypatch.setattr(connections, "_endpoint", fake.endpoint)
    app.dependency_overrides[db.get_pool] = lambda: None
    app.dependency_overrides[router.get_motis] = lambda: None
    app.dependency_overrides[router.motis_or_none] = lambda: None
    yield fake
    app.dependency_overrides.clear()
