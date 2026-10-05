"""A record of what was fetched from the data sources, for the statistics page.

Sources: `gtfs` (a timetable file downloaded), `import` (a window loaded into
the database), `gtfs-rt` (a real-time snapshot), `osm` (the street network).
Recording never stops the work it records: a failure is logged and skipped.
"""

import json
import logging

import asyncpg

log = logging.getLogger("transport_api.timetable.fetch_log")

KEEP_DAYS = 30


async def record(
    connection: asyncpg.Connection,
    source: str,
    *,
    name: str | None = None,
    bytes_: int | None = None,
    items: int | None = None,
    seconds: float | None = None,
    detail: dict | None = None,
) -> None:
    try:
        await connection.execute(
            "INSERT INTO rt.fetch_log (source, name, bytes, items, seconds, detail)"
            " VALUES ($1, $2, $3, $4, $5, $6::jsonb)",
            source,
            name,
            bytes_,
            items,
            seconds,
            json.dumps(detail, default=str) if detail is not None else None,
        )
    except Exception as exc:  # noqa: BLE001 - a record never stops the work it records
        log.warning("could not record a fetch of %s: %r", source, exc)


async def prune(connection: asyncpg.Connection) -> None:
    try:
        await connection.execute(
            f"DELETE FROM rt.fetch_log WHERE at < now() - interval '{KEEP_DAYS} days'"
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("could not prune the fetch log: %r", exc)
