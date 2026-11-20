"""The occupancy forecast of the railways into `rt.occupancy`.

SBB publishes, once a day, how full each train is expected to be on each
section of its run: for the next three months, in first and second class,
for its own trains and those of BLS, SOB, Thurbo and zb (operators 11, 33,
65, 82, 86). It is one ZIP of about 140 MB with a JSON file per operator and
day, free to download without a key:

    2026-11-20/operator-11.json
    {"operatorRef": "11", "opDate": "2026-11-20", "trains": [
      {"trainNumber": "707", "sections": [
        {"departureStationId": "8501008", "departureTime": "05:25:00",
         "expectedDepartureOccupancies": [
           {"fareClass": "firstClass", "occupancyLevel": "manySeatsAvailable"},
           ...]}, ...]}, ...]}

A train is the operator's number on its operating day, as in the timetable
(agency id, trip short name, service day); a section is where it leaves a
station. Only the next OCCUPANCY_DAYS days are kept: nobody asks further
ahead, and three months would be twenty million rows.
"""

import json
import logging
import os
import re
import time
import zipfile
from collections.abc import Iterable, Iterator
from datetime import date, timedelta
from pathlib import Path

import asyncpg
import httpx

from .. import settings

log = logging.getLogger("transport_api.timetable.occupancy")

# The levels of the forecast as one digit, the way /v1 counts capacity:
# 1 low, 2 medium, 3 high.
LEVELS = {"manySeatsAvailable": 1, "fewSeatsAvailable": 2, "standingRoomOnly": 3}
NAMES = {number: name for name, number in LEVELS.items()}

FILE = "occupancy.zip"
# The forecast is published once a night; fetching it twice a day finds it.
MAX_AGE_SECONDS = 12 * 3600

ENTRY = re.compile(r"(\d{4}-\d{2}-\d{2})/operator-(\w+)\.json")

Row = tuple[date, str, str, int, int | None, int | None]


def download(cache: Path, now: float | None = None) -> Path | None:
    """The forecast on disk, fetched again once it is half a day old.

    None when it is switched off. A failed download keeps the old file.
    """
    if not settings.OCCUPANCY_URL:
        return None
    path = cache / FILE
    now = time.time() if now is None else now
    if path.exists() and now - path.stat().st_mtime < MAX_AGE_SECONDS:
        return path
    cache.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    with httpx.stream(
        "GET",
        settings.OCCUPANCY_URL,
        follow_redirects=True,
        timeout=300,
        headers={"User-Agent": f"transport.opendata.ch/{settings.VERSION}"},
    ) as response:
        response.raise_for_status()
        with partial.open("wb") as out:
            for chunk in response.iter_bytes(1 << 20):
                out.write(chunk)
    os.replace(partial, path)
    log.info("occupancy forecast downloaded (%d MB)", path.stat().st_size >> 20)
    return path


def rows(path: Path, first: date, days: int) -> Iterator[Row]:
    """(day, operator, train number, DiDok number, first, second) for the days wanted.

    One file at a time: the one of SBB for a day is 40 MB of JSON.
    """
    wanted = {(first + timedelta(days=n)).isoformat() for n in range(days)}
    with zipfile.ZipFile(path) as archive:
        for name in sorted(archive.namelist()):
            match = ENTRY.fullmatch(name)
            if not match or match.group(1) not in wanted:
                continue
            with archive.open(name) as handle:
                yield from parse(json.load(handle))


def parse(document: dict) -> Iterator[Row]:
    day = date.fromisoformat(document["opDate"])
    operator = str(document["operatorRef"])
    for train in document.get("trains") or []:
        number = str(train.get("trainNumber") or "").strip()
        if not number:
            continue
        for section in train.get("sections") or []:
            station = str(section.get("departureStationId") or "")
            if not station.isdigit():
                continue
            levels = {
                o.get("fareClass", "").strip(): LEVELS.get(o.get("occupancyLevel", ""))
                for o in section.get("expectedDepartureOccupancies") or []
            }
            first, second = levels.get("firstClass"), levels.get("secondClass")
            if first is not None or second is not None:
                yield day, operator, number, int(station), first, second


async def store(connection: asyncpg.Connection, records: Iterable[Row]) -> int:
    """Replace the forecast with these rows, in one transaction; their number."""
    # A train that passes a station twice keeps its last word on it.
    unique = {r[:4]: r for r in records}
    async with connection.transaction():
        await connection.execute(
            """
            DROP TABLE IF EXISTS rt.occupancy_next;
            CREATE TABLE rt.occupancy_next (LIKE rt.occupancy INCLUDING ALL);
            """
        )
        await connection.copy_records_to_table(
            "occupancy_next",
            schema_name="rt",
            columns=("day", "operator", "train", "station", "first", "second"),
            records=unique.values(),
        )
        await connection.execute(
            """
            DROP TABLE rt.occupancy;
            ALTER TABLE rt.occupancy_next RENAME TO occupancy;
            """
        )
    return len(unique)


# The forecast of trains, by the train's operator, number and operating day.
QUERY = """
SELECT day, operator, train, station, first, second
FROM rt.occupancy
WHERE (day, operator, train) IN (
    SELECT * FROM unnest($1::date[], $2::text[], $3::text[])
)
"""


async def lookup(pool, trains: set[tuple[date, str, str]]) -> dict:
    """{(day, operator, train, DiDok number): (first, second)} for these trains."""
    if not trains:
        return {}
    days, operators, numbers = zip(*trains, strict=True)
    found = await pool.fetch(QUERY, list(days), list(operators), list(numbers))
    return {
        (r["day"], r["operator"], r["train"], r["station"]): (r["first"], r["second"])
        for r in found
    }
