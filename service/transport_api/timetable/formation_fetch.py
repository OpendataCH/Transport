"""Fetch train formations into `rt.formation`, within the key's quota.

The service answers one train per request, all its stops at once, and
allows 50 requests a minute and 20 000 a day. Some 11 000 trains run on a
weekday, so:

- **base**: every train once, three hours before it starts. There are no
  data more than about ten hours ahead, and none for another day than
  today's, so nothing can be loaded over night.
- **refresh**: long-distance trains and RE again 20 minutes before they start.
- **halfway**: those that run an hour or more once again on the way.
- **retry**: a train without a formation once more an hour before it starts.
- **early**: a train somebody asked `/v1/formation` for, up to ten hours ahead.

Replayed on the busiest day of the timetable (15 January 2027, 10 891
trains) that is 18 558 requests in any 24 hours with both caps used up, and
no train waits more than a minute. Each request is a row in
`rt.formation_call`, with whether the formation had changed: the quota is
counted from it, and it says whether the refreshes are worth theirs.

`formations_stop_based` rather than `_full`: the latter fails wherever the
service's two sources disagree, and has nothing more that is shown.
"""

import asyncio
import json
import logging
import time
from dataclasses import dataclass
from datetime import date, datetime, timedelta

import asyncpg
import httpx

from .. import settings
from ..mapping import ZURICH
from . import formation
from .mapping import moment

log = logging.getLogger("transport_api.timetable.formation")

URL = "https://api.opentransportdata.swiss/formation/v2/formations_stop_based"

PAUSE = 1.5  # seconds between requests: 40 a minute of the 50 allowed
PLAN_EVERY = 30  # seconds
TRAINS_EVERY = 1800  # seconds

REFRESH_BEFORE = timedelta(minutes=20)
RETRY_BEFORE = timedelta(minutes=60)
HALFWAY_FROM = timedelta(hours=1)
REFRESHED = ["IC", "ICN", "IR", "IRE", "EC", "EN", "ICE", "TGV", "RJX", "RJ", "NJ", "PE", "RE"]

PRIORITY = {"base": 0, "refresh": 1, "retry": 2, "halfway": 3, "early": 4}
CAPS = {"early": 2000, "retry": 1500}
# Of the day's budget, what only trains not asked yet may use.
RESERVE = 1000
# A train that starts after this belongs to the next day's numbers there.
NEXT_MORNING = 27 * 3600
KEEP_DAYS = 8

TRAINS = """
WITH running AS MATERIALIZED (
    SELECT a.name AS operator, ltrim(t.short_name, '0') AS number, r.category,
           t.idx, t.first_seq, t.last_seq
    FROM gtfs.service_dates d
    JOIN gtfs.trips t ON t.service = d.service
    JOIN gtfs.routes r ON r.idx = t.route
    JOIN gtfs.agency a ON a.idx = r.agency
    WHERE d.day = $1 AND t.mode = 'train' AND t.short_name <> '' AND a.name = ANY($2::text[])
)
SELECT x.operator, x.number, min(f.dep_s) AS starts, max(l.arr_s) AS ends,
       coalesce(bool_or(x.category = ANY($3::text[])), false) AS refreshed
FROM running x
JOIN gtfs.stop_times f ON f.trip = x.idx AND f.seq = x.first_seq
JOIN gtfs.stop_times l ON l.trip = x.idx AND l.seq = x.last_seq
GROUP BY 1, 2
"""

STATES = """
SELECT day, operator, number, asked_at, stops IS NOT NULL AS found, wanted
FROM rt.formation WHERE day >= $1
"""

USED = """
SELECT count(*) AS total,
       count(*) FILTER (WHERE reason = 'early') AS early,
       count(*) FILTER (WHERE reason = 'retry') AS retry
FROM rt.formation_call WHERE at > $1
"""

BEFORE = "SELECT stops FROM rt.formation WHERE day = $1 AND operator = $2 AND number = $3"

# No answer never replaces an answer.
STORE = """
INSERT INTO rt.formation (day, operator, number, asked_at, updated_at, stops)
VALUES ($1, $2, $3, $4::timestamptz,
        CASE WHEN $5::jsonb IS NULL THEN NULL ELSE $4::timestamptz END, $5::jsonb)
ON CONFLICT (day, operator, number) DO UPDATE SET
    asked_at = excluded.asked_at,
    updated_at = coalesce(excluded.updated_at, rt.formation.updated_at),
    stops = coalesce(excluded.stops, rt.formation.stops)
"""

CALLED = """
INSERT INTO rt.formation_call (at, day, operator, number, reason, status, changed)
VALUES ($1, $2, $3, $4, $5, $6, $7)
"""


@dataclass(frozen=True)
class Train:
    day: date  # the timetable's service day
    operator: str
    number: str
    operation: date  # the day the service knows it by
    starts: datetime
    ends: datetime
    refreshed: bool

    @property
    def key(self) -> tuple[date, str, str]:
        return self.day, self.operator, self.number


@dataclass(frozen=True)
class State:
    asked_at: datetime | None
    found: bool
    wanted: bool


@dataclass
class Used:
    total: int = 0
    early: int = 0
    retry: int = 0

    def add(self, reason: str) -> None:
        self.total += 1
        if reason in CAPS:
            setattr(self, reason, getattr(self, reason) + 1)


def operation_day(day: date, starts: int) -> date:
    return day + timedelta(days=1) if starts >= NEXT_MORNING else day


def due(train: Train, state: State | None, now: datetime) -> tuple[int, str] | None:
    """Why to ask for this train now, or None."""
    if now > train.ends or now.astimezone(ZURICH).date() != train.operation:
        return None
    midnight = datetime.combine(train.operation, datetime.min.time(), ZURICH)
    base = max(train.starts - formation.LEAD, midnight)
    asked = state.asked_at if state else None

    def passed(milestone: datetime) -> bool:
        return now >= milestone and (asked is None or asked < milestone)

    reason = None
    if passed(base):
        reason = "base"
    elif asked is None:
        if state and state.wanted and now >= train.starts - formation.HORIZON:
            reason = "early"
    elif now < base:
        pass
    elif not state.found:
        if passed(train.starts - RETRY_BEFORE):
            reason = "retry"
    elif train.refreshed:
        if passed(train.starts - REFRESH_BEFORE) and now < train.starts:
            reason = "refresh"
        elif train.ends - train.starts >= HALFWAY_FROM and passed(
            train.starts + (train.ends - train.starts) / 2
        ):
            reason = "halfway"
    return (PRIORITY[reason], reason) if reason else None


def allowed(reason: str, used: Used, budget: int) -> bool:
    if used.total >= budget:
        return False
    if reason in CAPS and getattr(used, reason) >= CAPS[reason]:
        return False
    reserve = min(RESERVE, budget // 10)
    return reason == "base" or used.total < budget - reserve


async def load_trains(connection: asyncpg.Connection, today: date) -> list[Train]:
    """Yesterday's that still run, today's, and tomorrow's after midnight."""
    trains = []
    operators, refreshed = list(formation.OPERATORS), REFRESHED
    for day in (today - timedelta(days=1), today, today + timedelta(days=1)):
        for row in await connection.fetch(TRAINS, day, operators, refreshed):
            operation = operation_day(day, row["starts"])
            if operation not in (today, today + timedelta(days=1)):
                continue
            trains.append(
                Train(
                    day,
                    row["operator"],
                    row["number"],
                    operation,
                    moment(day, row["starts"]),
                    moment(day, row["ends"]),
                    row["refreshed"],
                )
            )
    return trains


async def planned(
    connection: asyncpg.Connection, trains: list[Train], now: datetime, budget: int
) -> list[tuple[Train, str]]:
    """What to ask for now, the most pressing first, as far as the budget goes."""
    since = now.astimezone(ZURICH).date() - timedelta(days=2)
    states = {
        (r["day"], r["operator"], r["number"]): State(r["asked_at"], r["found"], r["wanted"])
        for r in await connection.fetch(STATES, since)
    }
    wanted = []
    for train in trains:
        found = due(train, states.get(train.key), now)
        if found:
            # Trains yet to leave before those on their way.
            wanted.append((found[0], train.starts < now, train.starts, train.key, train, found[1]))
    used = Used(**dict(await connection.fetchrow(USED, now - timedelta(days=1))))
    queue = []
    for *_, train, reason in sorted(wanted, key=lambda entry: entry[:4]):
        if allowed(reason, used, budget):
            used.add(reason)
            queue.append((train, reason))
    return queue


def compact(answer: object) -> list[dict] | None:
    """What is kept of an answer; None when it names no formation."""
    if not isinstance(answer, dict):
        return None
    stops = []
    for entry in answer.get("formationsAtScheduledStops") or []:
        short = entry.get("formationShort") or {}
        scheduled = entry.get("scheduledStop") or {}
        point, times = scheduled.get("stopPoint") or {}, scheduled.get("stopTime") or {}
        if not point.get("uic"):
            continue
        goals = []
        for goal in short.get("vehicleGoals") or []:
            end = goal.get("destinationStopPoint") or {}
            goals.append(
                {
                    "id": str(end["uic"]) if end.get("uic") else None,
                    "name": end.get("name"),
                    "first": goal.get("fromVehicleAtPosition"),
                    "last": goal.get("toVehicleAtPosition"),
                }
            )
        stops.append(
            {
                "station": str(point["uic"]),
                "arrival": times.get("arrivalTime"),
                "departure": times.get("departureTime"),
                "track": scheduled.get("track"),
                "formation": short.get("formationShortString"),
                "goals": goals,
            }
        )
    return stops if any(stop["formation"] for stop in stops) else None


async def store(
    connection: asyncpg.Connection,
    train: Train,
    reason: str,
    status: int | None,
    stops: list[dict] | None,
    now: datetime,
) -> None:
    before = await connection.fetchval(BEFORE, *train.key)
    changed = json.loads(before) != stops if before and stops else None
    await connection.execute(STORE, *train.key, now, json.dumps(stops) if stops else None)
    await connection.execute(CALLED, now, *train.key, reason, status, changed)


async def fetch_one(
    client: httpx.AsyncClient,
    connection: asyncpg.Connection,
    train: Train,
    reason: str,
    now: datetime,
) -> float:
    """Ask for one train; the seconds to pause after it."""
    status, stops, pause = None, None, 0
    try:
        response = await client.get(
            URL,
            params={
                "evu": formation.OPERATORS[train.operator],
                "operationDate": train.operation.isoformat(),
                "trainNumber": train.number,
            },
            headers={"Authorization": f"Bearer {settings.OTD_FORMATION_KEY}"},
        )
        status = response.status_code
        if status in (401, 403, 429):
            # Not the train's fault: it is asked for again.
            await connection.execute(CALLED, now, *train.key, reason, status, None)
            log.warning("formation service answered %d; waiting", status)
            return 60 if status == 429 else 600
        if status == 200:
            stops = compact(response.json())
        elif status >= 500:
            pause = 10
    except (httpx.HTTPError, ValueError, KeyError, TypeError, AttributeError) as exc:
        log.warning("formation of %s %s failed: %r", train.operator, train.number, exc)
        pause = 30
    await store(connection, train, reason, status, stops, now)
    return pause


async def prune(connection: asyncpg.Connection, today: date) -> None:
    await connection.execute("DELETE FROM rt.formation WHERE day < $1", today - timedelta(days=2))
    await connection.execute(
        "DELETE FROM rt.formation_call WHERE at < $1",
        datetime.now(ZURICH) - timedelta(days=KEEP_DAYS),
    )


async def keep_current(connect) -> None:
    """The loop; `connect` gives a database connection, waiting for one."""
    if not settings.OTD_FORMATION_KEY:
        log.info("no OTD_FORMATION_KEY: train formations are off")
        return
    connection = await connect()
    trains: list[Train] = []
    queue: list[tuple[Train, str]] = []
    trains_at = planned_at = float("-inf")
    trains_of = None
    async with httpx.AsyncClient(timeout=20) as client:
        while True:
            started, pause = time.monotonic(), 0.0
            try:
                now = datetime.now(ZURICH)
                if started - trains_at >= TRAINS_EVERY or now.date() != trains_of:
                    trains = await load_trains(connection, now.date())
                    await prune(connection, now.date())
                    trains_at, trains_of, planned_at = started, now.date(), float("-inf")
                if started - planned_at >= PLAN_EVERY:
                    queue = await planned(connection, trains, now, settings.FORMATION_PER_DAY)
                    planned_at = started
                if queue:
                    pause = await fetch_one(client, connection, *queue.pop(0), now)
            except Exception as exc:  # noqa: BLE001 - real time runs in the same process
                log.warning("formations failed: %r", exc)
                pause = 30
                if connection.is_closed():
                    connection = await connect()
            await asyncio.sleep(pause + max(0.0, PAUSE - (time.monotonic() - started)))
