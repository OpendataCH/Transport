"""The importer as the ingest process runs it: `python -m …importer`.

Needs TEST_DATABASE_URL like test_timetable_db.py. The permalinks are
replaced; the test feed is the small one in gtfs_feed.py.
"""

import asyncio
import os
from datetime import datetime
from pathlib import Path

import asyncpg
import httpx
import pytest
from gtfs_feed import TODAY, write_feed

from transport_api import settings
from transport_api.timetable import importer

DATABASE = os.environ.get("TEST_DATABASE_URL")
needs_database = pytest.mark.skipif(not DATABASE, reason="TEST_DATABASE_URL is not set")

# The client before any test replaces it.
CLIENT = httpx.Client


class Today(datetime):
    """The importer's clock, stopped on the test feed's day."""

    @classmethod
    def now(cls, tz=None):
        return datetime(TODAY.year, TODAY.month, TODAY.day, 12, tzinfo=tz)


@pytest.fixture
def window(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "DATABASE_URL", DATABASE)
    monkeypatch.setattr(settings, "GTFS_CACHE", str(tmp_path / "cache"))
    monkeypatch.setattr(settings, "GTFS_DAYS", 14)
    monkeypatch.setattr(settings, "GTFS_PAST_DAYS", 1)
    monkeypatch.setattr(importer, "datetime", Today)
    return tmp_path


async def _feed_file() -> str | None:
    connection = await asyncpg.connect(DATABASE)
    try:
        loaded = await importer.current_feed(connection)
        return loaded["feed_file"] if loaded else None
    finally:
        await connection.close()


@needs_database
def test_main_loads_the_feeds_given_and_points_the_router_at_them(window):
    feed = write_feed(window, "gtfs_main_20261001.zip")
    router_dir = window / "router"

    asyncio.run(importer.main([str(feed)], str(router_dir)))

    assert asyncio.run(_feed_file()) == "gtfs_main_20261001.zip"
    current = (router_dir / "CURRENT").read_text().strip()
    assert (router_dir / Path(current).name).exists()


@needs_database
def test_main_without_feeds_downloads_the_years_of_the_window(window, monkeypatch):
    fetched = []

    def feed_sources(url, first, last):
        return [("https://x/2026/permalink", "gtfs_dl_20261001.zip")]

    def download(url, cache):
        fetched.append(url)
        return write_feed(Path(cache), "gtfs_dl_20261001.zip")

    monkeypatch.setattr(importer, "feed_sources", feed_sources)
    monkeypatch.setattr(importer, "download", download)
    Path(settings.GTFS_CACHE).mkdir(parents=True)

    asyncio.run(importer.main([], None))

    assert fetched == ["https://x/2026/permalink"]
    assert asyncio.run(_feed_file()) == "gtfs_dl_20261001.zip"


@needs_database
def test_window_only_writes_the_loaded_window_again(window):
    cache = Path(settings.GTFS_CACHE)
    cache.mkdir(parents=True)
    feed = write_feed(cache, "gtfs_again_20261001.zip")
    asyncio.run(importer.main([str(feed)], None))
    router_dir = window / "router"

    asyncio.run(importer.main([], str(router_dir), window_only=True))

    assert (router_dir / "CURRENT").exists()


def test_window_only_needs_a_loaded_timetable(monkeypatch, window):
    async def connect(url):
        class Empty:
            async def fetchval(self, query):
                return False

            async def close(self):
                pass

        return Empty()

    monkeypatch.setattr(importer.asyncpg, "connect", connect)
    with pytest.raises(SystemExit, match="no timetable loaded"):
        asyncio.run(importer.main([], None, window_only=True))


def _http(monkeypatch, respond):
    """httpx, as the importer uses it, answered by `respond`."""
    transport = httpx.MockTransport(respond)

    def client(**kwargs):
        return CLIENT(transport=transport, **kwargs)

    def stream(method, url, **kwargs):
        kwargs.pop("timeout", None)
        return CLIENT(transport=transport, follow_redirects=True).stream(method, url)

    monkeypatch.setattr(importer.httpx, "Client", client)
    monkeypatch.setattr(importer.httpx, "stream", stream)


def test_the_permalink_names_the_feed_it_points_at(monkeypatch):
    def respond(request):
        if "2027" in request.url.path:
            return httpx.Response(404)
        if "moved" in request.url.path:
            return httpx.Response(302, headers={"location": "https://x/files/gtfs_20261008.zip"})
        return httpx.Response(200)

    _http(monkeypatch, respond)
    assert importer.feed_name("https://x/2026/moved") == "gtfs_20261008.zip"
    assert importer.feed_name("https://x/2026/gtfs_plain.zip") == "gtfs_plain.zip"
    assert importer.feed_name("https://x/2027/permalink") is None


def test_a_feed_is_downloaded_once_and_old_ones_go(monkeypatch, tmp_path):
    def respond(request):
        if request.method == "GET" and "permalink" in request.url.path:
            return httpx.Response(302, headers={"location": "https://x/files/gtfs_new.zip"})
        return httpx.Response(200, content=b"zip" * 10)

    _http(monkeypatch, respond)
    old = []
    for index in range(importer.KEPT_FEEDS + 1):
        path = tmp_path / f"gtfs_old{index}.zip"
        path.write_bytes(b"old")
        os.utime(path, (1_000_000 + index, 1_000_000 + index))
        old.append(path)

    path = importer.download("https://x/permalink", tmp_path)

    assert path == tmp_path / "gtfs_new.zip"
    assert path.read_bytes() == b"zip" * 10
    feeds = sorted(p.name for p in tmp_path.glob("*.zip"))
    assert len(feeds) == importer.KEPT_FEEDS
    assert not old[0].exists()
    # Already there: not fetched again.
    _http(monkeypatch, lambda request: httpx.Response(302, headers={"location": "/gtfs_new.zip"}))
    assert importer.download("https://x/permalink", tmp_path) == path
