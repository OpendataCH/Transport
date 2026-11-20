"""The loops of the ingest process, one round each, and the fetch log they keep.

The loops run forever; each test lets one round through and stops the next
wait. The network, the database and the importer are replaced.
"""

import asyncio
from datetime import datetime
from pathlib import Path

import asyncpg
import httpx
import pytest

from transport_api.timetable import fetch_log, ingest, realtime


class Stop(Exception):
    """Raised by the patched wait: one round is enough."""


class Connection:
    """An asyncpg connection that remembers what it was told, or fails."""

    def __init__(self, error: Exception | None = None) -> None:
        self.statements: list[tuple] = []
        self.error = error
        self.closed = False

    async def execute(self, statement, *args):
        if self.error is not None:
            raise self.error
        self.statements.append((statement, *args))

    async def close(self):
        self.closed = True

    def is_closed(self):
        return self.closed


@pytest.fixture
def one_round(monkeypatch):
    """Every wait of the loops is recorded, and the first ends the loop."""
    waits: list[float] = []

    async def sleep(seconds):
        waits.append(seconds)
        raise Stop

    monkeypatch.setattr(ingest.asyncio, "sleep", sleep)
    return waits


def connections_from(monkeypatch, *made: Connection) -> list[Connection]:
    queue = list(made)

    async def connect():
        return queue.pop(0)

    monkeypatch.setattr(ingest, "_connect", connect)
    return queue


def test_a_fetch_is_recorded_with_its_detail_as_json():
    connection = Connection()
    asyncio.run(
        fetch_log.record(
            connection, "gtfs", name="a.zip", bytes_=3, detail={"at": datetime(2026, 1, 1)}
        )
    )
    statement, *args = connection.statements[0]
    assert "INSERT INTO rt.fetch_log" in statement
    assert args == ["gtfs", "a.zip", 3, None, None, '{"at": "2026-01-01 00:00:00"}']


def test_the_fetch_log_never_stops_the_work(caplog):
    broken = Connection(OSError("gone"))
    asyncio.run(fetch_log.record(broken, "osm"))
    asyncio.run(fetch_log.prune(broken))
    assert "could not record a fetch of osm" in caplog.text
    assert "could not prune" in caplog.text


def test_the_fetch_log_keeps_thirty_days():
    connection = Connection()
    asyncio.run(fetch_log.prune(connection))
    assert "interval '30 days'" in connection.statements[0][0]


def test_run_creates_the_real_time_tables_once_and_starts_all_three(monkeypatch):
    setup = Connection()
    connections_from(monkeypatch, setup)
    started = []

    def task(name):
        async def loop(state):
            started.append((name, state))

        return loop

    monkeypatch.setattr(ingest, "_realtime", task("realtime"))
    monkeypatch.setattr(ingest, "_timetable", task("timetable"))

    async def forecast():
        started.append(("occupancy", None))

    monkeypatch.setattr(ingest, "_occupancy", forecast)
    asyncio.run(ingest.run())

    assert "rt." in setup.statements[0][0]
    assert setup.closed
    assert [name for name, _ in started] == ["realtime", "timetable", "occupancy"]
    assert started[0][1] is started[1][1]


def test_without_a_key_there_is_no_real_time(monkeypatch, caplog):
    monkeypatch.setattr(ingest.settings, "OTD_API_KEY", None)
    caplog.set_level("INFO")
    asyncio.run(ingest._realtime({"version": None}))
    assert "real time is off" in caplog.text


def _realtime_round(monkeypatch, fetch) -> tuple[dict, Connection, list]:
    monkeypatch.setattr(ingest.settings, "OTD_API_KEY", "key")
    connection = Connection()
    connections_from(monkeypatch, connection)
    monkeypatch.setattr(ingest.realtime, "fetch", fetch)
    stored = []

    async def store(_, snapshot):
        stored.append(snapshot)

    monkeypatch.setattr(ingest.realtime, "store", store)
    state = {"version": "20261001"}
    with pytest.raises(Stop):
        asyncio.run(ingest._realtime(state))
    return state, connection, stored


def test_a_round_of_real_time_is_stored_and_logged(monkeypatch, one_round):
    snapshot = realtime.Snapshot("20261008", None, [("t", None, 1, 2, None)], [], 7)
    monkeypatch.setattr(ingest.realtime, "parse", lambda payload: snapshot)

    async def fetch(client):
        return b"12345"

    state, connection, stored = _realtime_round(monkeypatch, fetch)

    assert state["version"] == "20261008"
    assert stored == [snapshot]
    _, source, name, size, items, *_ = connection.statements[0]
    assert (source, name, size, items) == ("gtfs-rt", "20261008", 5, 7)
    assert one_round[0] <= ingest.REALTIME_EVERY


def test_real_time_rate_limited_backs_off(monkeypatch, one_round):
    async def fetch(client):
        raise realtime.RateLimited("429")

    state, _, stored = _realtime_round(monkeypatch, fetch)

    assert stored == [] and state["version"] == "20261001"
    assert ingest.REALTIME_EVERY < one_round[0] <= ingest.BACKOFF


def test_real_time_failing_tries_again_on_the_next_round(monkeypatch, one_round, caplog):
    async def fetch(client):
        raise httpx.ConnectError("refused")

    _, _, stored = _realtime_round(monkeypatch, fetch)

    assert stored == []
    assert "real time failed" in caplog.text
    assert one_round[0] <= ingest.REALTIME_EVERY


def _timetable_round(monkeypatch, tmp_path, refresh, *, osm_url=None) -> Connection:
    monkeypatch.setattr(ingest.settings, "OTD_API_KEY", None)
    monkeypatch.setattr(ingest.settings, "GTFS_CACHE", str(tmp_path))
    monkeypatch.setattr(ingest.settings, "OSM_URL", osm_url)
    connection = Connection()
    connections_from(monkeypatch, connection)
    monkeypatch.setattr(ingest, "refresh_timetable", refresh)

    def refresh_osm():
        if osm_url:
            target = Path(tmp_path) / ingest.OSM_FILE
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"pbf")

    monkeypatch.setattr(ingest, "refresh_osm", refresh_osm)
    with pytest.raises(Stop):
        asyncio.run(ingest._timetable({"version": None}))
    return connection


def test_a_round_of_the_timetable_logs_a_new_street_network(monkeypatch, tmp_path, one_round):
    asked = []

    async def refresh(connection, version):
        asked.append(version)

    connection = _timetable_round(monkeypatch, tmp_path, refresh, osm_url="https://x/ch.pbf")

    assert asked == [None]
    sources = [args[1] for args in connection.statements if "INSERT" in args[0]]
    assert sources == ["osm"]
    assert any("DELETE" in args[0] for args in connection.statements)
    assert one_round == [ingest.TIMETABLE_EVERY]


def test_a_failed_refresh_tries_again_in_ten_minutes(monkeypatch, tmp_path, one_round, caplog):
    async def refresh(connection, version):
        raise RuntimeError("the import exited with 1")

    _timetable_round(monkeypatch, tmp_path, refresh)

    assert "timetable refresh failed" in caplog.text
    assert one_round == [600]


def test_the_timetable_waits_for_real_time_to_name_its_version(monkeypatch, tmp_path):
    monkeypatch.setattr(ingest.settings, "OTD_API_KEY", "key")
    monkeypatch.setattr(ingest.settings, "GTFS_CACHE", str(tmp_path))
    connections_from(monkeypatch, Connection())
    state = {"version": None}
    waits = []

    async def sleep(seconds):
        waits.append(seconds)
        if seconds == 5:
            state["version"] = "20261008"
            return
        raise Stop

    async def refresh(connection, version):
        assert version == "20261008"

    monkeypatch.setattr(ingest.asyncio, "sleep", sleep)
    monkeypatch.setattr(ingest, "refresh_timetable", refresh)
    monkeypatch.setattr(ingest, "refresh_osm", lambda: None)
    with pytest.raises(Stop):
        asyncio.run(ingest._timetable(state))
    assert waits == [5, ingest.TIMETABLE_EVERY]


def test_a_database_that_is_starting_is_waited_for(monkeypatch):
    attempts = []

    async def connect(url):
        attempts.append(url)
        if len(attempts) == 1:
            raise asyncpg.CannotConnectNowError("starting up")
        return "connection"

    async def sleep(seconds):
        pass

    monkeypatch.setattr(ingest.asyncpg, "connect", connect)
    monkeypatch.setattr(ingest.asyncio, "sleep", sleep)
    assert asyncio.run(ingest._connect()) == "connection"
    assert len(attempts) == 2


def test_the_forecast_is_loaded_again_only_when_file_or_day_change(monkeypatch, tmp_path):
    path = tmp_path / "occupancy.zip"
    path.write_bytes(b"")
    monkeypatch.setattr(ingest.occupancy, "download", lambda cache: path)
    monkeypatch.setattr(ingest.occupancy, "rows", lambda p, first, days: iter([("row",)]))
    stored = []

    async def store(connection, records):
        stored.append(list(records))
        return 1

    monkeypatch.setattr(ingest.occupancy, "store", store)
    connection = Connection()
    loaded = asyncio.run(ingest.refresh_occupancy(connection, None))
    assert stored == [[("row",)]]
    assert asyncio.run(ingest.refresh_occupancy(connection, loaded)) == loaded
    assert len(stored) == 1
    assert "rt.fetch_log" in connection.statements[0][0]
