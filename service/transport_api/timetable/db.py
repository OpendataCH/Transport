"""The connection pool to the timetable database."""

import asyncpg
from fastapi import Request

from .. import errors, settings


async def connect() -> asyncpg.Pool | None:
    """One pool per process, or None when no database is configured.

    Created lazily: a database that is not up yet when the service starts
    must not keep /v1 from answering.
    """
    if not settings.DATABASE_URL:
        return None
    return await asyncpg.create_pool(settings.DATABASE_URL, min_size=0, max_size=10)


async def fetch(pool: asyncpg.Pool, query: str, *args) -> list[asyncpg.Record]:
    """Rows, or a 503 before the first import has created the tables."""
    try:
        return await pool.fetch(query, *args)
    except asyncpg.UndefinedTableError as exc:
        raise errors.ApiError(503, "The timetable has not been loaded yet.") from exc
    except (OSError, asyncpg.CannotConnectNowError) as exc:
        raise errors.ApiError(503, "The timetable database is not reachable.") from exc


def get_pool(request: Request) -> asyncpg.Pool:
    """The pool, as a dependency; 503 in the /v1 envelope when there is none."""
    pool = getattr(request.app.state, "timetable", None)
    if pool is None:
        raise errors.ApiError(503, "The timetable database is not configured.")
    return pool
