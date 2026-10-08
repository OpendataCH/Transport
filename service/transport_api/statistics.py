"""The counters behind /stats.php, written the way the PHP application wrote them.

The keys are the PHP's, byte for byte - the daily sets and counters, the hashes
per resource and per exception class, and the hourly buckets - so that one
history runs on from 2012 across the change of implementation. The page itself
is `stats_page.py`.

The exception classes are recorded under the names the PHP gave them, where
the failure is the same one: a 404 is still a `NotFoundHttpException` on the
page. The classes that named a failure of search.ch stay in the history.

On top of what the PHP always counted there are four things (the PHP counted
them too in its last weeks, with the same rules):

- the kind of client per hour, from the User-Agent;
- the stations and the from → to pairs asked for, per day;
- the distinct clients per day, as keyed hashes of the address. The key rotates
  every day, and once the day is over only a summary is kept - how many, and
  how few of them made half and nine tenths of the calls. No address is stored.

Counting must never cost an answer. Every write is guarded; if Redis is slow or
gone the request is answered as if statistics did not exist, and the failure
is logged.
"""

import hashlib
import hmac
import logging
import re
import secrets
from datetime import datetime, timedelta
from urllib.parse import parse_qs
from zoneinfo import ZoneInfo

from . import settings

log = logging.getLogger(__name__)

ZONE = ZoneInfo(settings.TIMEZONE)

# Lifetimes, in seconds. The hourly buckets and the daily top lists feed the
# time windows of the page, which reach back 30 days.
HOURLY_TTL = 35 * 24 * 3600
TOP_TTL = 35 * 24 * 3600
# Today's client hashes only need to outlive the day; the margin covers a
# night in which nobody triggered the summary.
CLIENTS_TTL = 3 * 24 * 3600
SUMMARY_TTL = 400 * 24 * 3600

# A finished day keeps this many stations and pairs; today keeps all of them.
TOP_KEEP = 500

# Longest station or pair name recorded, so one odd query cannot bloat a set.
NAME_MAX = 80

# The PHP exception class names, for the failures that are the same failure.
EXCEPTION = "Exception"
NOT_FOUND = "Symfony\\Component\\HttpKernel\\Exception\\NotFoundHttpException"
METHOD_NOT_ALLOWED = "Symfony\\Component\\HttpKernel\\Exception\\MethodNotAllowedHttpException"
BAD_REQUEST = "Symfony\\Component\\HttpKernel\\Exception\\BadRequestHttpException"
HTTP_EXCEPTION = "Symfony\\Component\\HttpKernel\\Exception\\HttpException"
# A single value where a list belongs (see fields.NotAList). The PHP dies of a
# TypeError there and never reached its counter; here it is counted.
TYPE_ERROR = "TypeError"

# Kinds of client, first match wins. The PHP application used the same list in
# the same order; changing it changes what the history before and after means.
CLIENT_KINDS = [
    ("homeassistant", re.compile(r"homeassistant", re.I)),
    ("microcontroller", re.compile(r"esp32|esp8266|arduino|micropython", re.I)),
    ("app", re.compile(r"dalvik|cfnetwork|okhttp", re.I)),
    ("browser", re.compile(r"mozilla", re.I)),
    (
        "script",
        re.compile(
            r"python|aiohttp|node|axios|got \(|guzzle|curl|wget|java|jetty|go-http-client"
            r"|ruby|php|perl|postman|insomnia|reqwest|dart|apache-httpclient|powershell"
            r"|libwww|deno|bun/",
            re.I,
        ),
    ),
]

# Paths that are the service watching itself, not a client asking.
UNCOUNTED = ("/v1/health", "/v2/health")


def connect():
    """The Redis client, or None when statistics are switched off."""
    if settings.REDIS_URL is None:
        return None
    from redis import asyncio as aioredis

    return aioredis.from_url(
        settings.REDIS_URL,
        decode_responses=True,
        socket_timeout=settings.REDIS_TIMEOUT,
        socket_connect_timeout=settings.REDIS_TIMEOUT,
    )


def client_kind(user_agent: str | None) -> str:
    """The kind of client a User-Agent names: one of CLIENT_KINDS, or none/other."""
    if not user_agent or user_agent == "-":
        return "none"
    for kind, pattern in CLIENT_KINDS:
        if pattern.search(user_agent):
            return kind
    return "other"


def clean_name(value: str | None) -> str | None:
    """A station or place as asked for, with its whitespace tidied, or None."""
    if value is None:
        return None
    value = " ".join(value.split())
    return value[:NAME_MAX] or None


class Statistics:
    """Writes the counters for one answered request into Redis."""

    def __init__(self, redis) -> None:
        self._redis = redis
        self._secret: bytes | None = None
        self._rolled_over: str | None = None

    @property
    def redis(self):
        """The client, for the statistics page to read with."""
        return self._redis

    async def record(
        self,
        *,
        path: str,
        query: str,
        status: int,
        exception: str | None,
        client_ip: str | None,
        user_agent: str | None,
        now: datetime | None = None,
    ) -> None:
        now = (now or datetime.now(ZONE)).astimezone(ZONE)
        date = now.strftime("%Y-%m-%d")
        hour = now.strftime("%Y-%m-%dT%H")
        hourly = f"stats:hourly:{hour}"
        client_id = await self._client_id(date, client_ip)

        pipe = self._redis.pipeline(transaction=False)
        pipe.hincrby(hourly, f"client:{client_kind(user_agent)}", 1)

        if status == 429:
            # Neither a call nor an error, as in the PHP.
            pipe.hincrby(hourly, "ratelimited", 1)
        else:
            calls = f"stats:calls:{date}"
            pipe.sadd("stats:calls", calls)
            pipe.incr(calls)
            pipe.hincrby(hourly, "calls", 1)
            _count(pipe, "stats:resources", path, {"path": path})

            if exception is not None:
                errors = f"stats:errors:{date}"
                pipe.sadd("stats:errors", errors)
                pipe.incr(errors)
                pipe.hincrby(hourly, "errors", 1)
                pipe.hincrby(hourly, f"exception:{exception}", 1)
                _count(pipe, "stats:exceptions", exception, {"exception": exception})
            else:
                _count_places(pipe, date, path, query)

        if client_id is not None:
            clients = f"stats:clients:{date}"
            pipe.zincrby(clients, 1, client_id)
            pipe.expire(clients, CLIENTS_TTL)

        pipe.expire(hourly, HOURLY_TTL)
        await pipe.execute()

        await self._roll_over(now)

    async def _client_id(self, date: str, client_ip: str | None) -> str | None:
        """A hash of the address that means nothing outside the day it is made."""
        if not client_ip:
            return None
        if self._secret is None:
            await self._redis.set("stats:secret", secrets.token_hex(32), nx=True)
            self._secret = (await self._redis.get("stats:secret")).encode()
        digest = hmac.new(self._secret, f"{date}|{client_ip}".encode(), hashlib.sha256)
        return digest.hexdigest()[:16]

    async def _roll_over(self, now: datetime) -> None:
        """Once per day, whoever gets there first boils yesterday down.

        The flag in Redis is what makes it once, across processes and across
        the PHP and this service; the attribute only saves asking it again.
        """
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")
        if self._rolled_over == yesterday:
            return
        self._rolled_over = yesterday
        if not await self._redis.set(f"stats:rollover:{yesterday}", 1, nx=True, ex=CLIENTS_TTL):
            return

        for kind in ("stations", "routes"):
            await self._redis.zremrangebyrank(f"stats:top:{kind}:{yesterday}", 0, -TOP_KEEP - 1)

        clients = f"stats:clients:{yesterday}"
        members = await self._redis.zrange(clients, 0, -1, withscores=True)
        counts = [int(score) for _, score in members]
        if counts:
            summary = f"stats:clients:summary:{yesterday}"
            await self._redis.hset(summary, mapping=summarise(counts))
            await self._redis.expire(summary, SUMMARY_TTL)
        await self._redis.delete(clients)


def summarise(counts: list[int]) -> dict[str, int]:
    """How many clients there were, and how few of them made half and 90 % of the calls."""
    ordered = sorted(counts, reverse=True)
    total = sum(ordered)
    summary = {"clients": len(ordered), "requests": total, "half": 0, "ninety": 0, "top10": 0}
    running = 0
    for index, count in enumerate(ordered, start=1):
        running += count
        if not summary["half"] and running * 2 >= total:
            summary["half"] = index
        if not summary["ninety"] and running * 10 >= total * 9:
            summary["ninety"] = index
            break
    summary["top10"] = sum(ordered[:10])
    return summary


def _count(pipe, prefix: str, id_: str, data: dict[str, str]) -> None:
    """The PHP's Statistics::count(): a hash per item, its name in a set, and a counter."""
    key = f"{prefix}:{id_}"
    pipe.hset(key, mapping=data)
    pipe.sadd(prefix, key)
    pipe.hincrby(key, "calls", 1)


def _count_places(pipe, date: str, path: str, query: str) -> None:
    """The station of a board, or the pair of a connection search, as asked for."""
    params = parse_qs(query, keep_blank_values=False)

    def first(name: str) -> str | None:
        values = params.get(name)
        return values[0] if values else None

    if path.endswith("/stationboard"):
        station = clean_name(first("station") or first("id"))
        if station:
            key = f"stats:top:stations:{date}"
            pipe.zincrby(key, 1, station)
            pipe.expire(key, TOP_TTL)
    elif path.endswith("/connections"):
        origin, destination = clean_name(first("from")), clean_name(first("to"))
        if origin and destination:
            key = f"stats:top:routes:{date}"
            pipe.zincrby(key, 1, f"{origin} → {destination}")
            pipe.expire(key, TOP_TTL)


def exception_for(status: int, recorded: str | None) -> str | None:
    """The class an answer is counted under, or None when it is no error at all."""
    if recorded is not None:
        return recorded
    if status < 400 or status == 429:
        return None
    if status == 404:
        return NOT_FOUND
    if status == 405:
        return METHOD_NOT_ALLOWED
    if status == 400:
        return BAD_REQUEST
    if status < 500:
        return HTTP_EXCEPTION
    return EXCEPTION


class StatisticsMiddleware:
    """Counts every answered request once it has been answered.

    Pure ASGI rather than BaseHTTPMiddleware: it only watches the status go
    by. It must sit *inside* the proxy-headers middleware, or the address it
    sees is nginx's.
    """

    def __init__(self, app, statistics_of) -> None:
        self.app = app
        self._statistics_of = statistics_of

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] in UNCOUNTED:
            await self.app(scope, receive, send)
            return

        status = 500

        async def watch(message):
            nonlocal status
            if message["type"] == "http.response.start":
                status = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, watch)
        except Exception:
            await self._record(scope, 500)
            raise
        await self._record(scope, status)

    async def _record(self, scope, status: int) -> None:
        statistics = self._statistics_of()
        if statistics is None:
            return
        # The website and the statistics page mark their answers: they are not
        # the API, and the PHP never counted them either.
        if (scope.get("state") or {}).get("stats_skip"):
            return
        headers = dict(scope.get("headers") or [])
        client = scope.get("client")
        recorded = (scope.get("state") or {}).get("stats_exception")
        try:
            await statistics.record(
                path=scope["path"],
                query=scope.get("query_string", b"").decode("latin-1"),
                status=status,
                exception=exception_for(status, recorded),
                client_ip=client[0] if client else None,
                user_agent=headers.get(b"user-agent", b"").decode("latin-1") or None,
            )
        except Exception:
            log.warning("statistics not recorded", exc_info=True)
