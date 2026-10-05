"""A shared short memory of the answers that are asked again and again.

Thousands of displays and home automations ask for the same station board or
connection every minute. The answer cannot change faster than the real-time
feed, which is renewed every 30 seconds, so an answer given in the last 30
seconds is given again, from Redis, to every worker alike.

Connections asked "from now" are kept longer (CONNECTIONS_NOW_CACHE_SECONDS):
Home Assistant, nearly all of their traffic, asks the same connection every
90 seconds, which a 30-second memory never meets. Kept a little longer, every
second poll is answered here, at the price of delays up to that old.

Only what the service computes itself is kept: station boards and
connections under /v1 and /v2 when they answer from the timetable, and only
answers with status 200. The key is the path with its query, its parameters
sorted, so that `?a=1&b=2` and `?b=2&a=1` meet.

Pure ASGI, added inside the statistics middleware: a request answered from
here is still counted.
"""

import logging
from urllib.parse import parse_qsl, urlencode

from . import settings

log = logging.getLogger("transport_api.response_cache")

SECONDS = 30
CACHED_ENDPOINTS = ("/stationboard", "/connections")
PREFIX = "answer:"


def cached_path(path: str) -> bool:
    """Whether an answer to this path is kept."""
    if not path.endswith(CACHED_ENDPOINTS):
        return False
    if path.startswith("/v2/"):
        return True
    return path.startswith("/v1/") and settings.V1_FROM_TIMETABLE


def _pairs(query: bytes) -> list[tuple[str, str]]:
    return sorted(parse_qsl(query.decode("latin-1"), keep_blank_values=True))


def cache_key(path: str, query: bytes) -> str:
    return PREFIX + path + "?" + urlencode(_pairs(query))


def seconds_kept(path: str, query: bytes) -> int:
    """How long the answer is kept: longer for a connection from now."""
    if path.endswith("/connections"):
        asked = {name for name, value in _pairs(query) if value}
        if not asked & {"date", "time"}:
            return settings.CONNECTIONS_NOW_CACHE_SECONDS
    return SECONDS


class ResponseCacheMiddleware:
    def __init__(self, app, redis_of) -> None:
        self.app = app
        self._redis_of = redis_of

    async def __call__(self, scope, receive, send):
        redis = self._redis_of() if scope["type"] == "http" else None
        if redis is None or scope["method"] != "GET" or not cached_path(scope["path"]):
            await self.app(scope, receive, send)
            return

        key = cache_key(scope["path"], scope.get("query_string", b""))
        try:
            hit = await redis.hgetall(key)
        except Exception as exc:  # noqa: BLE001 - without the cache, answer as always
            log.warning("answer cache unreadable: %r", exc)
            hit = None
        if hit:
            await send(
                {
                    "type": "http.response.start",
                    "status": 200,
                    "headers": [(b"content-type", _bytes(hit.get("type") or hit.get(b"type")))],
                }
            )
            await send(
                {"type": "http.response.body", "body": _bytes(hit.get("body") or hit.get(b"body"))}
            )
            return

        start: dict | None = None
        body = bytearray()

        async def keep(message):
            nonlocal start
            if message["type"] == "http.response.start":
                start = message
            elif message["type"] == "http.response.body":
                body.extend(message.get("body", b""))
            await send(message)

        await self.app(scope, receive, keep)
        if start is None or start["status"] != 200:
            return
        content_type = dict(start.get("headers") or []).get(b"content-type", b"application/json")
        try:
            async with redis.pipeline(transaction=False) as pipe:
                pipe.hset(key, mapping={"type": content_type, "body": bytes(body)})
                pipe.expire(key, seconds_kept(scope["path"], scope.get("query_string", b"")))
                await pipe.execute()
        except Exception as exc:  # noqa: BLE001
            log.warning("answer cache unwritable: %r", exc)


def _bytes(value) -> bytes:
    if value is None:
        return b""
    # The Redis client decodes what it reads as UTF-8; the answers are JSON.
    return value if isinstance(value, bytes) else str(value).encode("utf-8")
