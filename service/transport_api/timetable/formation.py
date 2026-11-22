"""`/v1/formation`: the coaches of a train at each of its stops.

The railways' formations come from the Train Formation Service of
opentransportdata.swiss. formation_fetch.py asks it and keeps the answers in
`rt.formation`; this route only reads them, so that however many ask, the
service is asked no more often.

The service writes a formation as a short string:

    @A,F,F@B,[(1:11#NF,W2:12@C,2:13)#VH],F

- `@B` begins sector B of the platform.
- `[` and `]` hold the train. What is outside is empty platform (`F`) or
  parked coaches (`X`).
- `(` and `)` close a unit: no way through to the next coach.
- A coach is its kind, `:` its number, `#` what it offers. In front stands
  `-` closed, `>` groups board here, `=` reserved for groups in transit,
  `%` open but unattended.

**The first coach written is the front of the train, in the direction it
leaves in.** The cookbook does not say so; the data do (22 November 2026):
on each of 49 platforms seen with trains in both directions the sectors run
up for one and down for the other, the order of coach numbers reverses
exactly where trains reverse, and at buffer stops a departing train has the
empty platform written before it, an arriving one after it.

An answer is checked against the timetable stop by stop: for a number and a
day the service has answered with the run of the evening before.
"""

import json
import re
from datetime import date as Date  # noqa: N812 - `date` is a parameter here
from datetime import datetime, timedelta
from typing import Annotated, Any

import asyncpg
from fastapi import APIRouter, Depends, Query

from .. import errors
from ..encoding import PhpJson
from ..fields import Fields
from ..mapping import ZURICH, iso
from ..models import Errors, FormationResponse
from ..query import truthy
from . import db
from .mapping import location, moment, trip_ref
from .stationboard import CALLS

router = APIRouter()

# The operator as the timetable names it: as the formation service does.
# MBC and TRN are listed there too and had no coaches for any train asked.
OPERATORS = {
    "SBB": "SBBP",
    "BLS-bls": "BLSP",
    "THURBO": "THURBO",
    "RhB": "RhB",
    "SOB-sob": "SOB",
    "ZB": "ZB",
    "SZU": "SZU",
    "TPF": "TPF",
    "OeBB": "OeBB",
    "VDBB": "VDBB",
}

# A formation is loaded this long before the train starts ...
LEAD = timedelta(hours=3)
# ... and exists about this long before; asked for earlier, it is loaded then.
HORIZON = timedelta(hours=10)
# A stop of an answer is the timetable's when the planned times are this close.
TOLERANCE = timedelta(minutes=2)

KINDS: dict[str, tuple[str, list[int]]] = {
    "1": ("coach", [1]),
    "2": ("coach", [2]),
    "12": ("coach", [1, 2]),
    "K": ("coach", []),
    "FA": ("family", [2]),
    "CC": ("couchette", [2]),
    "WL": ("sleeper", []),
    "WR": ("restaurant", []),
    "W1": ("restaurant", [1]),
    "W2": ("restaurant", [2]),
    "LK": ("locomotive", []),
    "D": ("baggage", []),
    "X": ("parked", []),
}
OFFERS = {
    "BHP": "wheelchair",
    "BZ": "business",
    "FZ": "family",
    "KW": "stroller",
    "NF": "lowFloor",
    "VH": "bicycle",
    "VR": "bicycleReservation",
}

PART = re.compile(r"@([A-Z])|([^,@]+)")
COACH = re.compile(
    r"(?P<before>[\[\]()\-=>%]*)"
    r"(?P<kind>[0-9A-Z]{1,3})"
    r"(?P<after>[\])]*)"
    r"(?::(?P<number>[0-9]{1,4}))?"
    r"(?P<after_number>[\])]*)"
    r"(?:#(?P<offers>[A-Z;]+))?"
    r"(?P<end>[\])]*)"
)


def coaches(text: str | None) -> list[dict]:
    """The train's coaches, the front first; none when the string cannot be read."""
    if not text:
        return []
    bracketed = "[" in text
    inside, sector = not bracketed, None
    found: list[dict] = []
    for marker, part in PART.findall(text):
        if marker:
            sector = marker
            continue
        read = COACH.fullmatch(part.strip())
        if read is None:
            return []
        before = read["before"]
        after = read["after"] + read["after_number"] + read["end"]
        inside = inside or "[" in before
        kind = read["kind"]
        if inside and kind != "F":
            # A kind not known yet is still a coach: only not which.
            type_, classes = KINDS.get(kind, ("other", []))
            found.append(
                {
                    "position": len(found) + 1,
                    "sector": sector,
                    "number": read["number"],
                    "type": type_,
                    "classes": list(classes),
                    "offers": [OFFERS[o] for o in (read["offers"] or "").split(";") if o in OFFERS],
                    "closed": "-" in before,
                    "unattended": "%" in before,
                    "groupsBoarding": ">" in before,
                    "groupsInTransit": "=" in before,
                    "noPassageAhead": "(" in before,
                    "noPassageBehind": ")" in after,
                }
            )
        if bracketed and "]" in after:
            inside = False
    if bracketed and inside:
        return []  # cut off
    return found


def now() -> datetime:
    return datetime.now(ZURICH)


TRIP = """
SELECT t.idx, t.trip_id, t.short_name, t.mode, a.name AS operator,
       f.dep_s AS starts, l.arr_s AS ends
FROM gtfs.trips t
JOIN gtfs.routes r ON r.idx = t.route
LEFT JOIN gtfs.agency a ON a.idx = r.agency
JOIN gtfs.stop_times f ON f.trip = t.idx AND f.seq = t.first_seq
JOIN gtfs.stop_times l ON l.trip = t.idx AND l.seq = t.last_seq
WHERE t.trip_id = $1
  AND EXISTS (SELECT 1 FROM gtfs.service_dates sd
              WHERE sd.service = t.service AND sd.day = $2)
LIMIT 1
"""

KEPT = """
SELECT asked_at, updated_at, wanted, stops
FROM rt.formation WHERE day = $1 AND operator = $2 AND number = $3
"""

# Only a note for the loop that fetches: one row a train, however many ask.
WANT = """
INSERT INTO rt.formation (day, operator, number, wanted) VALUES ($1, $2, $3, true)
ON CONFLICT (day, operator, number) DO UPDATE SET wanted = true
RETURNING wanted
"""


@router.get(
    "/formation",
    summary="Get the coaches of a train at each of its stops",
    response_model=FormationResponse,
    responses={
        400: {"model": Errors, "description": "No `id`, or a bad `date`."},
        503: {"model": Errors, "description": "The timetable is not loaded."},
    },
)
async def get_formation(
    pool: Annotated[asyncpg.Pool, Depends(db.get_pool)],
    fields: Annotated[Fields, Depends(Fields.of)],
    id: Annotated[  # noqa: A002 - named as in the other routes
        str | None,
        Query(description="The trip's id, as `trip.id` of a station board or connection gives it."),
    ] = None,
    date: Annotated[
        str | None,
        Query(description="The service day, `trip.date`; today by default."),
    ] = None,
    fields_: Annotated[
        list[str] | None,
        Query(alias="fields[]", description="Keep only these parts of the answer."),
    ] = None,
) -> Any:
    """Coaches, sectors, classes and what each coach offers, the front first."""
    if not truthy(id):
        raise errors.ApiError(400, "Argument `id` is required.")
    try:
        day = Date.fromisoformat(date.strip()) if truthy(date) else now().date()
    except ValueError:
        raise errors.ApiError(400, "Argument `date` must be `YYYY-MM-DD`.") from None
    return PhpJson(content=fields.apply(await _formation(pool, id, day)))


async def _formation(pool: asyncpg.Pool, trip_id: str, day: Date) -> dict:
    answer = {
        "status": "unknown",
        "trip": trip_ref(trip_id, day),
        "updated": None,
        "availableFrom": None,
        "stops": [],
    }
    rows = await db.fetch(pool, TRIP, trip_id, day)
    if not rows:
        return answer
    trip = rows[0]
    if trip["mode"] != "train" or not trip["short_name"] or trip["operator"] not in OPERATORS:
        return {**answer, "status": "unsupported"}

    key = (day, trip["operator"], trip["short_name"].lstrip("0"))
    kept = await db.fetch(pool, KEPT, *key)
    state = kept[0] if kept else None
    starts, ends = moment(day, trip["starts"]), moment(day, trip["ends"])
    moment_now = now()

    if state is not None and state["stops"]:
        stops = await _stops(pool, trip["idx"], day, json.loads(state["stops"]))
        if any(stop["coaches"] for stop in stops):
            return {
                **answer,
                "status": "available",
                "updated": iso(state["updated_at"].astimezone(ZURICH)),
                "stops": stops,
            }

    # Asked early and without an answer, it is asked again at LEAD.
    tried = state is not None and state["asked_at"] is not None
    if moment_now > ends or (tried and state["asked_at"] >= starts - LEAD):
        return {**answer, "status": "none"}
    if starts - HORIZON <= moment_now < starts - LEAD and not (state and state["wanted"]):
        await db.fetch(pool, WANT, *key)
    if tried and moment_now >= starts - LEAD:
        return {**answer, "status": "none"}
    return {**answer, "status": "pending", "availableFrom": iso(starts - LEAD)}


async def _stops(pool: asyncpg.Pool, idx: int, day: Date, kept: list[dict]) -> list[dict]:
    """The trip's stops the answer knows, in the trip's order."""
    stops = []
    for call in await db.fetch(pool, CALLS, [idx], [day]):
        arrival, departure = moment(day, call["arr_s"]), moment(day, call["dep_s"])
        match = next(
            (
                stop
                for stop in kept
                if stop["station"] == str(call["id"])
                and (_near(stop["departure"], departure) or _near(stop["arrival"], arrival))
            ),
            None,
        )
        if match is None:
            continue
        stops.append(
            {
                "station": location(call["id"], call["name"], call["lat"], call["lon"]),
                "arrival": iso(arrival) if match["arrival"] else None,
                "departure": iso(departure) if match["departure"] else None,
                "platform": match["track"],
                "coaches": coaches(match["formation"]),
                "destinations": [
                    {
                        "id": goal["id"],
                        "name": goal["name"],
                        "fromPosition": goal["first"],
                        "toPosition": goal["last"],
                    }
                    for goal in match["goals"]
                ],
            }
        )
    return stops


def _near(given: str | None, planned: datetime) -> bool:
    if not given:
        return False
    try:
        return abs(datetime.fromisoformat(given) - planned) <= TOLERANCE
    except (TypeError, ValueError):
        return False
