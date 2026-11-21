"""GTFS-RT parsing, and the ingest loop's decision about which feed to load."""

import asyncio
import os
from datetime import date, datetime
from pathlib import Path

import asyncpg
import pytest
from google.transit import gtfs_realtime_pb2 as rt

from transport_api.timetable import ingest, realtime


def feed(*updates, version="20261001", timestamp=1791100000) -> bytes:
    message = rt.FeedMessage()
    message.header.gtfs_realtime_version = "2.0"
    message.header.timestamp = timestamp
    if version and hasattr(message.header, "feed_version"):
        message.header.feed_version = version
    for number, (trip_id, start_date, relationship, stops) in enumerate(updates):
        entity = message.entity.add()
        entity.id = str(number)
        entity.trip_update.trip.trip_id = trip_id
        if start_date:
            entity.trip_update.trip.start_date = start_date
        entity.trip_update.trip.schedule_relationship = relationship
        for sequence, arrival, departure, stop_relationship in stops:
            update = entity.trip_update.stop_time_update.add()
            if sequence is not None:
                update.stop_sequence = sequence
            if arrival is not None:
                update.arrival.delay = arrival
            if departure is not None:
                update.departure.delay = departure
            update.schedule_relationship = stop_relationship
    return message.SerializeToString()


SCHEDULED = rt.TripDescriptor.SCHEDULED
CANCELED = rt.TripDescriptor.CANCELED
STOP_SCHEDULED = rt.TripUpdate.StopTimeUpdate.SCHEDULED
SKIPPED = rt.TripUpdate.StopTimeUpdate.SKIPPED


def test_parse_turns_seconds_into_whole_minutes():
    snapshot = realtime.parse(
        feed(("t-1", "20261005", SCHEDULED, [(1, None, 90, STOP_SCHEDULED), (2, 29, 31, 0)]))
    )
    assert snapshot.delays == [
        ("t-1", date(2026, 10, 5), 1, None, 1),
        ("t-1", date(2026, 10, 5), 2, 0, 0),
    ]
    assert snapshot.trips == 1


def test_parse_cuts_the_seconds_off_both_ways():
    snapshot = realtime.parse(feed(("t-1", "20261005", SCHEDULED, [(1, -90, -29, 0)])))
    assert snapshot.delays[0][3:] == (-1, 0)


def test_parse_collects_cancellations_and_skips_what_cannot_be_placed():
    snapshot = realtime.parse(
        feed(
            ("t-cancelled", "20261005", CANCELED, []),
            ("t-no-date", "", SCHEDULED, [(1, 60, 60, 0)]),
            (
                "t-2",
                "20261005",
                SCHEDULED,
                [(None, 60, 60, 0), (3, 60, 60, SKIPPED), (4, None, None, 0)],
            ),
        )
    )
    assert snapshot.cancelled == [("t-cancelled", date(2026, 10, 5))]
    assert snapshot.skipped == [("t-2", date(2026, 10, 5), 3)]
    assert snapshot.delays == []


@pytest.mark.parametrize(
    ("name", "version"),
    [("gtfs_fp2026_20260930.zip", "20260930"), ("feed.zip", None)],
)
def test_version_of_reads_the_date_in_the_file_name(name, version):
    assert ingest.version_of(name) == version


class FakeConnection:
    pass


@pytest.fixture
def decide(monkeypatch, tmp_path):
    """Run refresh_timetable with the network and the loader replaced."""
    loads = []

    def run(loaded, newest, realtime_version, cached=()):
        for name in cached:
            (tmp_path / name).write_bytes(b"")

        async def current_feed(_):
            return loaded

        async def import_feed(paths):
            loads.append("+".join(path.name for path in paths))

        monkeypatch.setattr(ingest.settings, "GTFS_CACHE", str(tmp_path))
        monkeypatch.setattr(ingest.importer, "current_feed", current_feed)
        monkeypatch.setattr(ingest.importer, "feed_name", lambda url: newest)
        monkeypatch.setattr(ingest.importer, "download", lambda url, cache: Path(cache) / newest)
        monkeypatch.setattr(ingest, "import_feed", import_feed)
        asyncio.run(ingest.refresh_timetable(FakeConnection(), realtime_version))
        return loads

    return run


def _loaded(name, window_from):
    return {"feed_file": name, "window_from": window_from}


def test_first_import_takes_the_newest(decide):
    assert decide(None, "gtfs_20261001.zip", None) == ["gtfs_20261001.zip"]


def test_a_new_feed_waits_for_real_time(decide):
    today = ingest.datetime.now(ingest.importer.ZURICH).date()
    loaded = _loaded("gtfs_20260930.zip", today)
    assert decide(loaded, "gtfs_20261002.zip", "20260930") == []
    assert decide(loaded, "gtfs_20261002.zip", "20261002") == ["gtfs_20261002.zip"]


def test_without_real_time_the_newest_feed_is_taken(decide):
    today = ingest.datetime.now(ingest.importer.ZURICH).date()
    assert decide(_loaded("gtfs_20260930.zip", today), "gtfs_20261002.zip", None) == [
        "gtfs_20261002.zip"
    ]


def test_the_window_moves_on_daily(decide):
    old = date(2026, 1, 1)
    loads = decide(
        _loaded("gtfs_20260930.zip", old),
        "gtfs_20261002.zip",
        "20260930",
        cached=["gtfs_20260930.zip"],
    )
    assert loads == ["gtfs_20260930.zip"]


def test_nothing_to_do(decide):
    today = ingest.datetime.now(ingest.importer.ZURICH).date()
    assert decide(_loaded("gtfs_20260930.zip", today), "gtfs_20260930.zip", None) == []


DATABASE = os.environ.get("TEST_DATABASE_URL")


@pytest.mark.skipif(not DATABASE, reason="TEST_DATABASE_URL is not set")
def test_store_replaces_the_previous_snapshot():
    async def scenario():
        connection = await asyncpg.connect(DATABASE)
        try:
            await connection.execute(ingest.importer.sql("realtime.sql"))
            first = realtime.parse(
                feed(
                    ("t-1", "20261005", SCHEDULED, [(1, 60, 60, 0)]),
                    ("t-x", "20261005", CANCELED, []),
                    ("t-y", "20261005", SCHEDULED, [(2, None, None, SKIPPED)]),
                )
            )
            await realtime.store(connection, first)
            second = realtime.parse(feed(("t-2", "20261005", SCHEDULED, [(1, 120, 120, 0)])))
            await realtime.store(connection, second)
            delays = await connection.fetch("SELECT trip_id, departure_delay FROM rt.stop_delay")
            cancelled = await connection.fetchval("SELECT count(*) FROM rt.trip_cancelled")
            skipped = await connection.fetchval("SELECT count(*) FROM rt.stop_skipped")
            await connection.execute("TRUNCATE rt.stop_delay, rt.trip_cancelled, rt.stop_skipped")
            return [tuple(r) for r in delays], cancelled + skipped
        finally:
            await connection.close()

    delays, cancelled = asyncio.run(scenario())
    assert delays == [("t-2", 2)]
    assert cancelled == 0


class FakeProcess:
    def __init__(self, code: int) -> None:
        self.code = code

    async def wait(self) -> int:
        return self.code


@pytest.mark.parametrize("code", [0, 1])
def test_the_import_runs_as_a_child_that_also_writes_the_window(monkeypatch, tmp_path, code):
    calls = []

    async def spawn(*args):
        calls.append(args)
        return FakeProcess(code)

    monkeypatch.setattr(ingest.settings, "GTFS_CACHE", str(tmp_path))
    monkeypatch.setattr(ingest.asyncio, "create_subprocess_exec", spawn)
    feed_path = tmp_path / "gtfs_20261002.zip"

    if code == 0:
        asyncio.run(ingest.import_feed([feed_path]))
    else:
        with pytest.raises(RuntimeError):
            asyncio.run(ingest.import_feed([feed_path]))
    assert calls[0][-3:] == (str(feed_path), "--window-feed", str(tmp_path))


def test_a_week_back_is_not_a_stale_window(decide, monkeypatch):
    monkeypatch.setattr(ingest.settings, "GTFS_PAST_DAYS", 7)
    today = ingest.datetime.now(ingest.importer.ZURICH).date()
    loaded = _loaded("gtfs_20260930.zip", today - ingest.timedelta(days=7))
    assert decide(loaded, "gtfs_20260930.zip", None) == []


def test_a_window_to_the_end_of_the_feed_only_changes_with_the_feed(decide, monkeypatch):
    monkeypatch.setattr(ingest.settings, "GTFS_DAYS", 0)
    old = date(2026, 1, 1)
    assert decide(_loaded("gtfs_20260930.zip", old), "gtfs_20260930.zip", None) == []


def test_the_street_network_is_fetched_when_missing_and_renewed_when_old(monkeypatch, tmp_path):
    fetched = []

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def raise_for_status(self):
            pass

        def iter_bytes(self, size):
            fetched.append(size)
            yield b"pbf"

    monkeypatch.setattr(ingest.settings, "GTFS_CACHE", str(tmp_path))
    monkeypatch.setattr(ingest.settings, "OSM_URL", "https://example.org/ch.osm.pbf")
    monkeypatch.setattr(ingest.httpx, "stream", lambda *a, **k: Response())

    path = ingest.refresh_osm(now=1_000_000_000)
    assert path.read_bytes() == b"pbf"
    assert len(fetched) == 1
    # Fresh: left alone. Older than the limit: fetched again.
    ingest.refresh_osm(now=path.stat().st_mtime + 86400)
    assert len(fetched) == 1
    ingest.refresh_osm(now=path.stat().st_mtime + 31 * 86400)
    assert len(fetched) == 2


def test_without_an_osm_url_nothing_is_fetched(monkeypatch):
    monkeypatch.setattr(ingest.settings, "OSM_URL", None)
    assert ingest.refresh_osm() is None


def test_two_timetable_years_are_imported_together(monkeypatch, tmp_path):
    # Next year's feed is out: the window reads both, as one import.
    names = {"2026": "gtfs_fp2026_20260930.zip", "2027": "gtfs_fp2027_20260930.zip"}
    loads = []

    async def current_feed(_):
        return None

    async def import_feed(paths):
        loads.append([p.name for p in paths])

    def feed_name(url):
        return next((n for year, n in names.items() if year in url), None)

    monkeypatch.setattr(ingest.settings, "GTFS_CACHE", str(tmp_path))
    monkeypatch.setattr(
        ingest.settings, "GTFS_URL", "https://x/timetable-{year}-gtfs2020/permalink"
    )
    monkeypatch.setattr(ingest.settings, "GTFS_DAYS", 120)
    monkeypatch.setattr(ingest.importer, "current_feed", current_feed)
    monkeypatch.setattr(ingest.importer, "feed_name", feed_name)
    monkeypatch.setattr(
        ingest.importer, "download", lambda url, cache: Path(cache) / feed_name(url)
    )
    monkeypatch.setattr(ingest, "import_feed", import_feed)
    monkeypatch.setattr(
        ingest, "datetime", type("D", (), {"now": staticmethod(lambda tz: datetime(2026, 11, 1))})
    )
    asyncio.run(ingest.refresh_timetable(FakeConnection(), None))
    assert loads == [[names["2026"], names["2027"]]]
