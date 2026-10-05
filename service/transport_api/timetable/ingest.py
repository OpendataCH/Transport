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
from . import fetch_log, importer, realtime

log = logging.getLogger("transport_api.timetable.ingest")

REALTIME_EVERY = 30
TIMETABLE_EVERY = 3600
BACKOFF = 120


def version_of(feed_file: str) -> str | None:
    """`gtfs_fp2026_20260930.zip` -> `20260930`."""
    match = re.search(r"(\d{8})", feed_file)
    return match.group(1) if match else None


async def refresh_timetable(connection: asyncpg.Connection, realtime_version: str | None) -> None:
    """Import the feeds real time is on, and re-import them to move the window.

    The window may need two timetable years; what is loaded is recorded as
    their file names joined by `+`, and a new file for either is a new import.
    """
    today = datetime.now(importer.ZURICH).date()
    cache = Path(settings.GTFS_CACHE)
    loaded = await importer.current_feed(connection)
    first, last = importer.window_of(today, settings.GTFS_DAYS, settings.GTFS_PAST_DAYS)
    sources = await asyncio.to_thread(importer.feed_sources, settings.GTFS_URL, first, last)
    if not sources:
        log.warning("no timetable feed found for %s..%s", first, last)
        return
    newest = "+".join(name for _, name in sources)

    target = newest
    if loaded is not None and newest != loaded["feed_file"]:
        newest_version = max(filter(None, (version_of(n) for _, n in sources)), default=None)
        if realtime_version and newest_version and newest_version > realtime_version:
            log.info("%s waits for real time to leave version %s", newest, realtime_version)
            target = loaded["feed_file"]

    # A window that ends a fixed number of days ahead moves on, in steps of
    # GTFS_WINDOW_STEP_DAYS; one that runs to the end of the feed only changes
    # with the feed.
    stale = (
        loaded is not None
        and settings.GTFS_DAYS > 0
        and loaded["window_from"]
        < today - timedelta(days=settings.GTFS_PAST_DAYS + settings.GTFS_WINDOW_STEP_DAYS - 1)
    )
    if loaded is not None and target == loaded["feed_file"] and not stale:
        return

    if target == newest:
        paths = []
        for url, name in sources:
            fresh = not (cache / name).exists()
            started = time.monotonic()
            path = await asyncio.to_thread(importer.download, url, cache)
            if path.name != name:
                log.info("the permalink moved on to %s; deciding again next round", path.name)
                return
            if fresh and path.exists():
                await fetch_log.record(
                    connection,
                    "gtfs",
                    name=path.name,
                    bytes_=path.stat().st_size,
                    seconds=round(time.monotonic() - started, 1),
                    detail={"version": version_of(path.name)},
                )
            paths.append(path)
    else:
        paths = [cache / name for name in target.split("+")]
        missing = [p.name for p in paths if not p.exists()]
        if missing:
            log.warning("%s no longer in the cache; the window stays where it is", missing)
            return

    await import_feed(paths)


OSM_FILE = "osm/switzerland.osm.pbf"


def refresh_osm(now: float | None = None) -> Path | None:
    """The street network for the router, fetched when missing or too old.

    docker/motis-run.sh notices the new file by its size and rebuilds; until
    the first download it routes without streets, as before.
    """
    if not settings.OSM_URL:
        return None
    target = Path(settings.GTFS_CACHE) / OSM_FILE
    now = time.time() if now is None else now
    if target.exists() and now - target.stat().st_mtime < settings.OSM_MAX_AGE_DAYS * 86400:
        return target
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = target.with_name(target.name + ".part")
    with httpx.stream("GET", settings.OSM_URL, follow_redirects=True, timeout=600) as response:
        response.raise_for_status()
        with partial.open("wb") as out:
            for chunk in response.iter_bytes(1 << 20):
                out.write(chunk)
    partial.rename(target)
    log.info("street network for the router: %d MB", target.stat().st_size >> 20)
    return target


async def import_feed(paths: list[Path]) -> None:
    """Run the importer as a child process; its log lines go to ours."""
    # The child also writes the loaded window for the router and points
    # docker/motis-run.sh at it, so that both answer from the same timetable.
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "transport_api.timetable.importer",
        *(str(path) for path in paths),
        "--window-feed",
        settings.GTFS_CACHE,
    )
    code = await process.wait()
    if code != 0:
        raise RuntimeError(f"the import of {'+'.join(p.name for p in paths)} exited with {code}")


async def run() -> None:
    # The real-time tables are created once, here: two tasks doing it at the
    # same time on an empty database collide in Postgres' catalogue, even with
    # IF NOT EXISTS.
    connection = await _connect()
    await connection.execute(importer.sql("realtime.sql"))
    await connection.close()
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
                payload = await realtime.fetch(client)
                fetched = time.monotonic() - started
                snapshot = realtime.parse(payload)
                state["version"] = snapshot.version or state["version"]
                await realtime.store(connection, snapshot)
                await fetch_log.record(
                    connection,
                    "gtfs-rt",
                    name=snapshot.version,
                    bytes_=len(payload),
                    items=snapshot.trips,
                    seconds=round(fetched, 2),
                    detail={"delays": len(snapshot.delays), "cancelled": len(snapshot.cancelled)},
                )
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
            osm = Path(settings.GTFS_CACHE) / OSM_FILE
            before = osm.stat().st_mtime if osm.exists() else None
            started = time.monotonic()
            await asyncio.to_thread(refresh_osm)
            if settings.OSM_URL and osm.exists() and osm.stat().st_mtime != before:
                await fetch_log.record(
                    connection,
                    "osm",
                    name=osm.name,
                    bytes_=osm.stat().st_size,
                    seconds=round(time.monotonic() - started, 1),
                )
            await fetch_log.prune(connection)
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
            return await asyncpg.connect(settings.DATABASE_URL)
        except (OSError, asyncpg.CannotConnectNowError) as exc:
            log.info("waiting for the database: %r", exc)
            await asyncio.sleep(2)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    # Every fetch, twice a minute, would otherwise be a line in the log.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    asyncio.run(run())
