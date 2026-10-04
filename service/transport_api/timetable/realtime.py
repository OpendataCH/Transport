"""GTFS-RT trip updates into `rt.stop_delay` and `rt.trip_cancelled`.

The feed is the whole picture every time - every known change in the next
three hours - so each fetch replaces the tables rather than amending them.
The rows are written into fresh tables and swapped in, which keeps readers
from waiting on the write.

The free plan allows five requests a minute; the server caches for thirty
seconds, so fetching more often than twice a minute buys nothing anyway.
"""

import logging
from dataclasses import dataclass
from datetime import UTC, date, datetime

import asyncpg
import httpx
from google.transit import gtfs_realtime_pb2

from .. import settings

log = logging.getLogger("transport_api.timetable.realtime")

CANCELED = gtfs_realtime_pb2.TripDescriptor.CANCELED
SKIPPED = gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.SKIPPED
NO_DATA = gtfs_realtime_pb2.TripUpdate.StopTimeUpdate.NO_DATA


class RateLimited(Exception):
    """429 from the API; the caller should wait before the next fetch."""


@dataclass
class Snapshot:
    version: str | None
    timestamp: datetime | None
    delays: list[tuple[str, date, int, int | None, int | None]]
    cancelled: list[tuple[str, date]]
    trips: int


async def fetch(client: httpx.AsyncClient) -> bytes:
    response = await client.get(
        settings.GTFS_RT_URL,
        headers={
            "Authorization": f"Bearer {settings.OTD_API_KEY}",
            # The API refuses requests without one.
            "User-Agent": f"transport.opendata.ch/{settings.VERSION}",
        },
    )
    if response.status_code == 429:
        raise RateLimited(response.text[:200])
    response.raise_for_status()
    return response.content


def parse(payload: bytes) -> Snapshot:
    """The trip updates as rows. Delays become whole minutes, as search.ch has them.

    A stop time update without a stop sequence cannot be placed in the
    timetable and is skipped, as are skipped stops and stops without data.
    Trips that are not in the timetable at all (added trips) have no stop
    times to put a delay on, so they come through but match nothing.
    """
    feed = gtfs_realtime_pb2.FeedMessage()
    feed.ParseFromString(payload)

    delays: list[tuple[str, date, int, int | None, int | None]] = []
    cancelled: list[tuple[str, date]] = []
    trips = 0
    for entity in feed.entity:
        if not entity.HasField("trip_update"):
            continue
        update = entity.trip_update
        trip = update.trip
        if not trip.trip_id or not trip.start_date:
            continue
        day = datetime.strptime(trip.start_date, "%Y%m%d").date()
        trips += 1
        if trip.schedule_relationship == CANCELED:
            cancelled.append((trip.trip_id, day))
            continue
        for stop in update.stop_time_update:
            if not stop.HasField("stop_sequence"):
                continue
            if stop.schedule_relationship in (SKIPPED, NO_DATA):
                continue
            arrival = _minutes(stop.arrival) if stop.HasField("arrival") else None
            departure = _minutes(stop.departure) if stop.HasField("departure") else None
            if arrival is None and departure is None:
                continue
            delays.append((trip.trip_id, day, stop.stop_sequence, arrival, departure))

    header = feed.header
    return Snapshot(
        version=getattr(header, "feed_version", None) or None,
        timestamp=datetime.fromtimestamp(header.timestamp, UTC) if header.timestamp else None,
        delays=delays,
        cancelled=cancelled,
        trips=trips,
    )


def _minutes(event) -> int | None:
    """Seconds late, rounded to the minute; half a minute rounds away from zero."""
    if not event.HasField("delay"):
        return None
    seconds = event.delay
    minutes = (abs(seconds) + 30) // 60
    return minutes if seconds >= 0 else -minutes


async def store(connection: asyncpg.Connection, snapshot: Snapshot) -> None:
    """Replace the real-time tables with this snapshot, in one transaction."""
    async with connection.transaction():
        await connection.execute(
            """
            DROP TABLE IF EXISTS rt.stop_delay_next, rt.trip_cancelled_next;
            CREATE TABLE rt.stop_delay_next (LIKE rt.stop_delay INCLUDING ALL);
            CREATE TABLE rt.trip_cancelled_next (LIKE rt.trip_cancelled INCLUDING ALL);
            """
        )
        # The feed can repeat a stop; the last word on it wins.
        unique = {(t, d, s): (t, d, s, a, p) for t, d, s, a, p in snapshot.delays}
        await connection.copy_records_to_table(
            "stop_delay_next",
            schema_name="rt",
            columns=("trip_id", "day", "seq", "arrival_delay", "departure_delay"),
            records=unique.values(),
        )
        await connection.copy_records_to_table(
            "trip_cancelled_next",
            schema_name="rt",
            columns=("trip_id", "day"),
            records=set(snapshot.cancelled),
        )
        await connection.execute(
            """
            DROP TABLE rt.stop_delay;
            DROP TABLE rt.trip_cancelled;
            ALTER TABLE rt.stop_delay_next RENAME TO stop_delay;
            ALTER TABLE rt.trip_cancelled_next RENAME TO trip_cancelled;
            """
        )
        await connection.execute(
            "INSERT INTO rt.feed (fetched_at, feed_timestamp, trips, delays)"
            " VALUES (now(), $1, $2, $3)",
            snapshot.timestamp,
            snapshot.trips,
            len(unique),
        )
        # One row per fetch is plenty for a day's look back, not for ever.
        await connection.execute("DELETE FROM rt.feed WHERE fetched_at < now() - interval '1 day'")
    log.info(
        "real time: %d trips, %d stop delays, %d cancelled, feed version %s",
        snapshot.trips,
        len(unique),
        len(snapshot.cancelled),
        snapshot.version,
    )
