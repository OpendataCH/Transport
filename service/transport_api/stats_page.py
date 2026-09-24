"""`/stats`, the statistics page, answered the way the PHP page `/stats.php` did.

The old address and its four shapes are a contract of their own: `?format=json`
(calls and errors per day since 2012), `?format=csv` (the same as a file),
`?format=window&window=…` (one time window in detail) and, without a format,
the page. Scripts and dashboards elsewhere read the first three, so they keep
the PHP's keys, key order, number types and escaping.

Reading only. What is counted, and how, is `statistics.py`; the keys read here
are the ones written there and, before September 2026, by the PHP application.
"""

import json
import math
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, PlainTextResponse, Response
from jinja2 import Environment, FileSystemLoader, select_autoescape

from .encoding import PhpErrorJson
from .statistics import ZONE, summarise

router = APIRouter()

TEMPLATES = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html"]),
)

# The time windows the error details can be narrowed to, key => label.
WINDOWS = {
    "1h": "Last hour",
    "2h": "Last 2 hours",
    "6h": "Last 6 hours",
    "12h": "Last 12 hours",
    "24h": "Last 24 hours",
    "48h": "Last 48 hours",
    "7d": "Last 7 days",
    "14d": "Last 14 days",
    "30d": "Last 30 days",
    "all": "Since 2015",
}

# What the kinds of client in statistics.CLIENT_KINDS are called on the page.
CLIENT_KIND_LABELS = {
    "homeassistant": "Home Assistant",
    "browser": "Browsers and displays",
    "script": "Scripts and servers",
    "microcontroller": "Microcontrollers (ESP32 …)",
    "app": "Mobile apps",
    "none": "No user agent",
    "other": "Other",
}

# A short explanation for each exception class the page lists. The class names
# are the PHP's; the Python service records its failures under the same names.
KNOWN_EXCEPTIONS = {
    "Symfony\\Component\\HttpKernel\\Exception\\MethodNotAllowedHttpException": (
        "405",
        "Request used an HTTP method other than GET",
    ),
    "Exception": (
        "500",
        "timetable.search.ch answered with a server error, an error message or invalid JSON",
    ),
    "Buzz\\Exception\\RequestException": (
        "500",
        "Connection to timetable.search.ch failed or timed out",
    ),
    "Buzz\\Exception\\ClientException": (
        "500",
        "HTTP client error while calling timetable.search.ch",
    ),
    "Symfony\\Component\\Debug\\Exception\\ContextErrorException": (
        "500",
        "PHP warning or notice inside the API (a bug)",
    ),
    "Symfony\\Component\\HttpKernel\\Exception\\NotFoundHttpException": ("404", "Unknown path"),
    "Symfony\\Component\\HttpKernel\\Exception\\BadRequestHttpException": (
        "400",
        "Missing or invalid parameters",
    ),
    "Symfony\\Component\\HttpKernel\\Exception\\HttpException": (
        "4xx",
        "Other HTTP error raised by the API",
    ),
    "Predis\\ClientException": ("500", "Statistics store (Redis) rejected a command"),
    "Predis\\Response\\ServerException": ("500", "Statistics store (Redis) returned an error"),
    "Predis\\Connection\\ConnectionException": ("500", "Statistics store (Redis) unreachable"),
    "TypeError": (
        "500",
        "A single value where the API expects a list, e.g. fields= without brackets",
    ),
}


# /stats is the name; /stats.php is where the page has always been, and keeps
# answering the same - not by redirect, because a script fetching
# ?format=json with a plain HTTP client may not follow one.
@router.get("/stats", include_in_schema=False)
@router.get("/stats.php", include_in_schema=False)
async def stats_page(request: Request) -> Response:
    # The website is not the API; the statistics middleware leaves it uncounted.
    request.state.stats_skip = True

    statistics = getattr(request.app.state, "statistics", None)
    if statistics is None:
        return HTMLResponse('No Redis configured. See section "Statistics" in README.md.')
    reader = Reader(statistics.redis)

    format_ = request.query_params.get("format")
    if format_ == "window":
        return PhpErrorJson(await window(reader, request.query_params.get("window")))

    calls = await reader.calls()
    errors = await reader.errors()
    data = [
        {"date": date, "calls": _int(value), "errors": _int(errors.get(date))}
        for date, value in calls.items()
    ]

    if format_ == "csv":
        lines = ["Date,Calls,Errors"] + [f"{r['date']},{r['calls']},{r['errors']}" for r in data]
        return PlainTextResponse(
            "\n".join(lines),
            media_type="text/csv",
            headers={"Content-Disposition": "attachment;filename=transport.csv"},
        )

    if format_ == "json":
        return PhpErrorJson({"data": data})

    error_years = by_year(data)

    values = [_int(value) for value in calls.values()]
    total = sum(values)
    page = TEMPLATES.get_template("stats.html")
    initial = await window(reader, "all")
    return HTMLResponse(
        page.render(
            total=total,
            avg=total / max(len(values), 1),
            max=max(values, default=0),
            resources=await reader.top("stats:resources", ["path", "calls"]),
            stations=await recent_stations(reader, datetime.now(ZONE).date()),
            # The PHP's all-time list, frozen since June 2017, kept as history.
            historic_stations=await reader.top("stats:stations", ["name", "x", "y", "calls"], 10),
            errors=[
                describe(e) for e in await reader.top("stats:exceptions", ["exception", "calls"])
            ],
            error_years=error_years,
            years_json=twig_json(years_chart(data, error_years)),
            windows=WINDOWS,
            windows_json=twig_json(list(WINDOWS)),
            window=initial,
            window_json=twig_json(initial),
        )
    )


# How far back the station box on the page looks.
RECENT_DAYS = 30


async def recent_stations(reader: "Reader", today) -> list[dict]:
    """The station boards most asked for over the last RECENT_DAYS days.

    This replaces the PHP's all-time list, which stopped counting on 8 June
    2017 when the API moved to search.ch and had shown the same five names ever
    since. The daily lists behind it are counted from 24 September 2026 on.
    """
    dates = [(today - timedelta(days=i)).isoformat() for i in range(RECENT_DAYS - 1, -1, -1)]
    return [
        {"name": str(name), "calls": int(requests)}
        for name, requests in await reader.top_places("stations", dates, 5)
    ]


class Reader:
    """The PHP's Statistics getters, over the async Redis client."""

    def __init__(self, redis) -> None:
        self._redis = redis

    async def calls(self) -> dict[str, str]:
        return await self._daily("stats:calls")

    async def errors(self) -> dict[str, str]:
        return await self._daily("stats:errors")

    async def _daily(self, prefix: str) -> dict[str, str]:
        """date => counter, oldest first, from the set of daily keys."""
        flat = await self._redis.sort(prefix, get=["#", "*"], alpha=True)
        cut = len(prefix) + 1
        return {
            key[cut : cut + 10]: value for key, value in zip(flat[::2], flat[1::2], strict=True)
        }

    async def top(self, key: str, fields: list[str], limit: int = 5) -> list[dict]:
        """The items of a counted set, most calls first."""
        flat = await self._redis.sort(
            key,
            by="*->calls",
            start=0,
            num=limit,
            get=[f"*->{field}" for field in fields],
            desc=True,
        )
        size = len(fields)
        rows = [flat[i : i + size] for i in range(0, len(flat), size)]
        return [dict(zip(fields, row, strict=True)) for row in rows]

    async def hourly(self, hours: int, now: float) -> list[dict]:
        """The hourly buckets of the last `hours` hours, oldest first, this hour included."""
        starts = [datetime.fromtimestamp(now - i * 3600, ZONE) for i in range(hours - 1, -1, -1)]
        pipe = self._redis.pipeline(transaction=False)
        for start in starts:
            pipe.hgetall(f"stats:hourly:{start:%Y-%m-%dT%H}")
        buckets = await pipe.execute()

        result = []
        for start, bucket in zip(starts, buckets, strict=True):
            bucket = bucket or {}
            exceptions, clients = {}, {}
            for field, value in bucket.items():
                if field.startswith("exception:"):
                    exceptions[field[10:]] = int(value)
                elif field.startswith("client:"):
                    clients[field[7:]] = int(value)
            result.append(
                {
                    "hour": f"{start:%Y-%m-%dT%H}:00",
                    "recorded": bool(bucket),
                    "calls": int(bucket.get("calls", 0)),
                    "errors": int(bucket.get("errors", 0)),
                    "ratelimited": int(bucket.get("ratelimited", 0)),
                    "exceptions": exceptions,
                    "clients": clients,
                }
            )
        return result

    async def days(self, days: int, today) -> dict[str, dict]:
        """Calls and errors of the last `days` calendar days, oldest first, today included."""
        dates = [(today - timedelta(days=i)).isoformat() for i in range(days - 1, -1, -1)]
        calls = await self._redis.mget([f"stats:calls:{d}" for d in dates])
        errors = await self._redis.mget([f"stats:errors:{d}" for d in dates])
        return {
            d: {"calls": _int(c), "errors": _int(e)}
            for d, c, e in zip(dates, calls, errors, strict=True)
        }

    async def top_places(self, kind: str, dates: list[str], count: int = 10) -> list[tuple]:
        """The most asked-for stations or pairs over some days, as (name, requests)."""
        keys = [f"stats:top:{kind}:{d}" for d in dates]
        if not keys:
            return []
        if len(keys) == 1:
            return await self._redis.zrevrange(keys[0], 0, count - 1, withscores=True)
        # ZUNION answers lowest first, ties in ascending order; reversed, that is
        # exactly ZREVRANGE's order over the union.
        union = await self._redis.zunion(keys, withscores=True)
        return list(reversed(union))[:count]

    async def recorded_place_days(self, dates: list[str]) -> list[str]:
        """The days among `dates` that have any station or pair counted, oldest first."""
        return [
            d
            for d in dates
            if await self._redis.exists(f"stats:top:stations:{d}", f"stats:top:routes:{d}")
        ]

    async def client_days(self, dates: list[str], today: str) -> dict[str, dict]:
        """Distinct clients per day: a finished day's summary, today counted live."""
        result = {}
        for date in dates:
            if date == today:
                members = await self._redis.zrange(f"stats:clients:{date}", 0, -1, withscores=True)
                counts = [int(score) for _, score in members]
                if counts:
                    result[date] = summarise(counts)
            else:
                summary = await self._redis.hgetall(f"stats:clients:summary:{date}")
                if summary:
                    result[date] = {field: int(value) for field, value in summary.items()}
        return result


async def window(reader: Reader, key: str | None, now: datetime | None = None) -> dict:
    """Errors by class, and calls, errors and rate-limited requests over time, for one window.

    Hour windows are read from the hourly buckets alone. Day windows are
    calendar days: calls and errors come from the daily counters, which go back
    to 2012; the split by error class and the rate-limited requests only exist
    in the hourly buckets. "all" uses the all-time totals by class and lists the
    last 14 days.
    """
    if key not in WINDOWS:
        key = "24h"
    now = (now or datetime.now(ZONE)).astimezone(ZONE)
    unit = key[-1]
    size = int(key[:-1]) if key != "all" else 0

    daily = {}
    if unit == "h":
        buckets = await reader.hourly(size, now.timestamp())
        rows = [
            {
                "start": b["hour"],
                "calls": b["calls"] if b["recorded"] else None,
                "errors": b["errors"] if b["recorded"] else None,
                "ratelimited": b["ratelimited"] if b["recorded"] else None,
            }
            for b in buckets
        ]
    else:
        days = 14 if key == "all" else size
        buckets = await reader.hourly((days - 1) * 24 + now.hour + 1, now.timestamp())
        daily = await reader.days(days, now.date())

        ratelimited: dict[str, int] = {}
        for b in buckets:
            if b["recorded"]:
                date = b["hour"][:10]
                ratelimited[date] = ratelimited.get(date, 0) + b["ratelimited"]

        rows = [
            {
                "start": date,
                "calls": day["calls"],
                "errors": day["errors"],
                "ratelimited": ratelimited.get(date),
            }
            for date, day in daily.items()
        ]

    by_class: dict[str, int] = {}
    if key == "all":
        for e in await reader.top("stats:exceptions", ["exception", "calls"], 100):
            by_class[e["exception"]] = _int(e["calls"])
    else:
        for b in buckets:
            for name, count in b["exceptions"].items():
                by_class[name] = by_class.get(name, 0) + count
        by_class = _descending(by_class)
    class_total = sum(by_class.values())
    exceptions = []
    for name, count in by_class.items():
        exception = describe({"exception": name, "calls": count})
        exception["share"] = _share(count, class_total)
        exceptions.append(exception)

    if unit == "h":
        dates = list(dict.fromkeys(b["hour"][:10] for b in buckets))
    else:
        dates = list(daily)

    kinds: dict[str, int] = {}
    for b in buckets:
        for kind, count in b["clients"].items():
            kinds[kind] = kinds.get(kind, 0) + count
    kinds = _descending(kinds)
    kinds_total = sum(kinds.values())
    client_kinds = [
        {
            "kind": kind,
            "label": CLIENT_KIND_LABELS.get(kind, kind),
            "requests": count,
            "share": _share(count, kinds_total),
        }
        for kind, count in kinds.items()
    ]

    sums, hours = [0] * 24, [0] * 24
    for b in buckets:
        if b["recorded"]:
            hour_of_day = int(b["hour"][11:13])
            sums[hour_of_day] += b["calls"] + b["ratelimited"]
            hours[hour_of_day] += 1
    profile = [_round(s / h) if h else None for s, h in zip(sums, hours, strict=True)]

    async def top(kind: str) -> list[dict]:
        return [
            {"name": str(name), "requests": int(requests)}
            for name, requests in await reader.top_places(kind, dates)
        ]

    client_days = [
        {"date": date, **summary}
        for date, summary in (await reader.client_days(dates, now.date().isoformat())).items()
    ]

    # The places are counted per calendar day, so the tables cover whole days
    # whatever the window says; the page names the days it actually shows.
    place_days = await reader.recorded_place_days(dates)
    places_days = (
        {
            "from": place_days[0],
            "to": place_days[-1],
            "untilNow": place_days[-1] == now.date().isoformat(),
        }
        if place_days
        else None
    )

    since = next((b["hour"] for b in buckets if b["recorded"]), None)
    return {
        "window": key,
        "label": WINDOWS[key],
        "granularity": "hour" if unit == "h" else "day",
        "since": since,
        "calls": sum(r["calls"] or 0 for r in rows),
        "errors": sum(r["errors"] or 0 for r in rows),
        "ratelimited": None if since is None else sum(r["ratelimited"] or 0 for r in rows),
        "classTotal": class_total,
        "exceptions": exceptions,
        "rows": list(reversed(rows)),
        "clientKinds": client_kinds,
        "kindsTotal": kinds_total,
        "clientDays": list(reversed(client_days)),
        "stations": await top("stations"),
        "routes": await top("routes"),
        "placesDays": places_days,
        "profile": profile,
    }


def describe(error: dict) -> dict:
    """Adds a short name, the HTTP status and a plain explanation to an exception counter."""
    name = error["exception"]
    namespace, _, short = name.rpartition("\\")
    status, description = KNOWN_EXCEPTIONS.get(name, ("", ""))
    return {
        "exception": name,
        "calls": _int(error["calls"]),
        "name": short,
        "namespace": namespace,
        "status": status,
        "description": description,
    }


def number(value) -> str:
    """Twig's number_format(0, ".", "'"): rounded half up, thousands apart by '."""
    rounded = int(Decimal(str(value)).quantize(Decimal(1), rounding=ROUND_HALF_UP))
    return f"{rounded:,}".replace(",", "'")


def twig_json(value) -> str:
    """Twig's json_encode: ASCII only and slashes escaped, as PHP's json_encode."""
    return json.dumps(value, ensure_ascii=True, separators=(",", ":")).replace("/", "\\/")


def _int(value) -> int:
    """PHP's (int) of a Redis answer: missing or empty is 0."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _share(part: int, whole: int):
    """100 * part / whole as PHP computes it: an int when it divides evenly."""
    if not whole:
        return 0
    if (100 * part) % whole == 0:
        return 100 * part // whole
    return 100 * part / whole


def _round(value: float) -> int:
    """PHP's round(): half away from zero, not to even."""
    return int(math.floor(value + 0.5))


def _descending(counts: dict[str, int]) -> dict[str, int]:
    """PHP's arsort(): by value, highest first, ties in their original order."""
    return dict(sorted(counts.items(), key=lambda item: -item[1]))


TEMPLATES.filters["number"] = number


# Errors were counted from this day on; before it, a day's 0 means "not counted".
ERRORS_SINCE = "2015-11-22"


def by_year(data: list[dict]) -> list[dict]:
    """Calls, errors and the error rate per year, newest first.

    A year before ERRORS_SINCE has no errors (None, not 0). In the year it falls
    in, only the days from then on count, so the rate compares like with like.
    """
    years: dict[str, dict] = {}
    for row in data:
        key = row["date"][:4]
        year = years.setdefault(key, {"year": key, "calls": 0, "errors": None, "since": None})
        if row["date"] < ERRORS_SINCE:
            continue
        if year["errors"] is None:
            year["errors"] = 0
            if row["date"][5:] != "01-01":
                year["since"] = row["date"]
        year["calls"] += row["calls"]
        year["errors"] += row["errors"]
    for key, year in years.items():
        if year["errors"] is None:
            year["calls"] = sum(r["calls"] for r in data if r["date"][:4] == key)
    return list(reversed(years.values()))


def years_chart(data: list[dict], years: list[dict]) -> list[dict]:
    """The yearly figures for the two charts above the table, oldest first.

    The calls are the whole year's, unlike the table's: the table counts the
    year errors began in only from then on, so that its rate compares like with
    like, but as a bar that year would look like a slump. The rate stays the
    table's, as a number of percent, and None where errors were not counted.
    """
    calls: dict[str, int] = {}
    for row in data:
        calls[row["date"][:4]] = calls.get(row["date"][:4], 0) + row["calls"]
    return [
        {
            "year": y["year"],
            "calls": calls[y["year"]],
            "rate": None
            if y["errors"] is None or not y["calls"]
            else 100 * y["errors"] / y["calls"],
            "since": y["since"],
        }
        for y in reversed(years)
    ]


def rate(errors: int | None, calls: int) -> str:
    """An error rate as the page shows it: three decimals, a dash without calls."""
    if errors is None or not calls:
        return "–"
    value = 100 * errors / calls
    if 0 < value < 0.001:
        return "< 0.001 %"
    return f"{value:.3f} %"


TEMPLATES.filters["rate"] = rate
