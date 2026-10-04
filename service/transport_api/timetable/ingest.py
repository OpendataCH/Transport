"""The loop that keeps the timetable database current.

    python -m transport_api.timetable.ingest

One process, in its own container: the API runs several workers, and each
polling on its own would multiply the requests against a limit of five a
minute. Timetable and real time are two tasks of it, and an import runs in a
child process, so that real time keeps coming in while a feed is read - which
takes ten minutes on a slow disk and happens every day.

- **Timetable**, checked hourly. A new feed is imported once the real-time
  feed has moved to its version - the trip ids of real time belong to one
  timetable version, and the switch happens at 3 p.m. on the day after
  publication. Importing earlier would leave every delay matching nothing
  for hours. The same feed is re-imported each day to move the window on.
- **Real time**, every 30 seconds, when OTD_API_KEY is set.
"""

import asyncio
import logging
import re
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import asyncpg
import httpx

from .. import settings
from . import importer, realtime

log = logging.getLogger("transport_api.timetable.ingest")

REALTIME_EVERY = 30
TIMETABLE_EVERY = 3600
BACKOFF = 120


def version_of(feed_file: str) -> str | None:
    """`gtfs_fp2026_20260930.zip` -> `20260930`."""
    match = re.search(r"(\d{8})", feed_file)
    return match.group(1) if match else None


async def refresh_timetable(connection: asyncpg.Connection, realtime_version: str | None) -> None:
    """Import the feed real time is on, and re-import it daily to move the window."""
    today = datetime.now(importer.ZURICH).date()
    cache = Path(settings.GTFS_CACHE)
    loaded = await importer.current_feed(connection)
    newest = await asyncio.to_thread(importer.feed_name, settings.GTFS_URL)

    target = newest
    if loaded is not None and newest != loaded["feed_file"]:
        newest_version = version_of(newest)
        if realtime_version and newest_version and newest_version > realtime_version:
            log.info("%s waits for real time to leave version %s", newest, realtime_version)
            target = loaded["feed_file"]

    stale = (
        loaded is not None
        and settings.GTFS_DAYS > 0
        and loaded["window_from"] < today - timedelta(days=1)
    )
    if loaded is not None and target == loaded["feed_file"] and not stale:
        return

    if target == newest:
        path = await asyncio.to_thread(importer.download, settings.GTFS_URL, cache)
        if path.name != target:
            log.info("the permalink moved on to %s; deciding again next round", path.name)
            return
    else:
        path = cache / target
        if not path.exists():
            log.warning("%s is no longer in the cache; the window stays where it is", target)
            return

    await import_feed(path)


async def import_feed(path: Path) -> None:
    """Run the importer as a child process; its log lines go to ours."""
    process = await asyncio.create_subprocess_exec(
        sys.executable, "-m", "transport_api.timetable.importer", str(path)
    )
    code = await process.wait()
    if code != 0:
        raise RuntimeError(f"the import of {path.name} exited with {code}")
    # The router (docker/motis-run.sh) follows this file, so that it routes
    # on the same timetable the database holds.
    marker = Path(settings.GTFS_CACHE) / "CURRENT"
    marker.write_text(path.name + "\n")


async def run() -> None:
    state: dict[str, str | None] = {"version": None}
    await asyncio.gather(_realtime(state), _timetable(state))


async def _realtime(state: dict[str, str | None]) -> None:
    if not settings.OTD_API_KEY:
        log.info("no OTD_API_KEY: real time is off")
        return
    connection = await _connect()
    async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
        while True:
            started = time.monotonic()
            wait = REALTIME_EVERY
            try:
                snapshot = realtime.parse(await realtime.fetch(client))
                state["version"] = snapshot.version or state["version"]
                await realtime.store(connection, snapshot)
            except realtime.RateLimited as exc:
                log.warning("real time rate limited (%s); waiting", exc)
                wait = BACKOFF
            except (httpx.HTTPError, asyncpg.PostgresError, OSError) as exc:
                log.warning("real time failed: %r", exc)
            if connection.is_closed():
                connection = await _connect()
            await asyncio.sleep(max(0.0, wait - (time.monotonic() - started)))


async def _timetable(state: dict[str, str | None]) -> None:
    connection = await _connect()
    # With a key, learn real time's version first: a feed imported before
    # real time has moved to it would match no delay for hours.
    for _ in range(24):
        if state["version"] or not settings.OTD_API_KEY:
            break
        await asyncio.sleep(5)
    while True:
        wait = TIMETABLE_EVERY
        try:
            await refresh_timetable(connection, state["version"])
        except (httpx.HTTPError, asyncpg.PostgresError, OSError, RuntimeError) as exc:
            log.error("timetable refresh failed: %r", exc)
            wait = 600
        if connection.is_closed():
            connection = await _connect()
        await asyncio.sleep(wait)


async def _connect() -> asyncpg.Connection:
    """Wait for the database rather than crash while it starts."""
    while True:
        try:
            connection = await asyncpg.connect(settings.DATABASE_URL)
            await connection.execute(importer.sql("realtime.sql"))
            return connection
        except (OSError, asyncpg.CannotConnectNowError) as exc:
            log.info("waiting for the database: %r", exc)
            await asyncio.sleep(2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Every fetch, twice a minute, would otherwise be a line in the log.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(run())
