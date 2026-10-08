"""The counters behind /stats.php: the PHP's keys, written by this service."""

import asyncio
from datetime import datetime, timedelta

import fakeredis
import pytest

from transport_api import errors, statistics
from transport_api.main import app

ZONE = statistics.ZONE


@pytest.fixture
def redis():
    """A fake Redis the service writes to, and a synchronous view to read it back."""
    server = fakeredis.FakeServer()
    app.state.statistics = statistics.Statistics(
        fakeredis.FakeAsyncRedis(server=server, decode_responses=True)
    )
    yield fakeredis.FakeRedis(server=server, decode_responses=True)
    app.state.statistics = None


def today() -> str:
    return datetime.now(ZONE).strftime("%Y-%m-%d")


def this_hour() -> str:
    return "stats:hourly:" + datetime.now(ZONE).strftime("%Y-%m-%dT%H")


def board(client, **headers):
    return client.get("/v1/stationboard", params={"station": "Bern", "limit": "3"}, headers=headers)


def test_a_call_is_counted_in_the_keys_the_php_writes(client, timetable, redis):
    assert board(client).status_code == 200

    calls = f"stats:calls:{today()}"
    assert redis.sismember("stats:calls", calls)
    assert redis.get(calls) == "1"
    assert redis.hgetall("stats:resources:/v1/stationboard") == {
        "path": "/v1/stationboard",
        "calls": "1",
    }
    assert redis.hget(this_hour(), "calls") == "1"
    assert 0 < redis.ttl(this_hour()) <= statistics.HOURLY_TTL


def test_the_station_asked_for_is_counted_for_the_day(client, timetable, redis):
    board(client)
    board(client)

    assert redis.zscore(f"stats:top:stations:{today()}", "Bern") == 2


def test_a_connection_search_counts_the_pair(client, timetable, redis):
    client.get("/v1/connections", params={"from": " Lausanne ", "to": "Genève"})

    assert redis.zscore(f"stats:top:routes:{today()}", "Lausanne → Genève") == 1


def test_a_rate_limited_request_is_neither_call_nor_error(client, timetable, redis):
    timetable.raises(errors.ApiError(429, "Rate limit error: too many requests at the moment."))

    assert client.get("/v1/locations", params={"query": "Bern"}).status_code == 429

    assert redis.hget(this_hour(), "ratelimited") == "1"
    assert redis.get(f"stats:calls:{today()}") is None
    assert redis.get(f"stats:errors:{today()}") is None


def test_an_outage_is_counted_apart_from_a_bug(client, timetable, redis):
    timetable.raises(errors.ApiError(503, "The router is not reachable."))

    assert client.get("/v1/connections", params={"from": "Bern", "to": "Thun"}).status_code == 503

    name = statistics.SERVICE_UNAVAILABLE
    assert redis.get(f"stats:errors:{today()}") == "1"
    assert redis.hget(f"stats:exceptions:{name}", "calls") == "1"
    # A failed call is still a call, as in the PHP.
    assert redis.get(f"stats:calls:{today()}") == "1"
    assert redis.zcard(f"stats:top:routes:{today()}") == 0


def test_a_failure_inside_is_a_plain_exception(client, timetable, redis):
    timetable.raises(errors.ApiError(500, "DateTime::__construct(): Failed to parse time string"))

    assert client.get("/v1/stationboard", params={"station": "Bern"}).status_code == 500

    assert redis.hget("stats:exceptions:Exception", "calls") == "1"


def test_an_unknown_path_is_a_not_found(client, redis):
    assert client.get("/v1/nowhere").status_code == 404

    assert redis.hget(f"stats:exceptions:{statistics.NOT_FOUND}", "calls") == "1"


def test_the_health_check_is_not_a_client(client, redis):
    client.get("/v2/health")

    assert redis.keys("stats:*") == []


def test_clients_are_told_apart_by_the_forwarded_address(client, timetable, redis):
    board(client, **{"X-Forwarded-For": "192.0.2.1"})
    board(client, **{"X-Forwarded-For": "192.0.2.1"})
    board(client, **{"X-Forwarded-For": "192.0.2.2"})

    members = redis.zrange(f"stats:clients:{today()}", 0, -1, withscores=True)
    assert sorted(score for _, score in members) == [1, 2]
    # Hashes, never the address itself.
    assert all("192.0.2" not in member for member, _ in members)


def test_the_kind_of_client_is_counted_per_hour(client, timetable, redis):
    board(client, **{"User-Agent": "HomeAssistant/2026.9.3 aiohttp/3.14.3"})

    assert redis.hget(this_hour(), "client:homeassistant") == "1"


@pytest.mark.parametrize(
    "user_agent, kind",
    [
        ("HomeAssistant/2026.9.3 aiohttp/3.14.3 Python/3.14", "homeassistant"),
        ("ESP32HTTPClient", "microcontroller"),
        ("Dalvik/2.1.0 (Linux; U; Android 14)", "app"),
        ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/605.1.15", "browser"),
        ("python-requests/2.34.2", "script"),
        ("got (https://github.com/sindresorhus/got)", "script"),
        ("mobilitepourtous.ch/1.0 (+https://mobilitepourtous.ch)", "other"),
        ("-", "none"),
        (None, "none"),
    ],
)
def test_client_kinds(user_agent, kind):
    assert statistics.client_kind(user_agent) == kind


def test_a_redis_failure_costs_no_answer(client, timetable):
    class Broken:
        async def record(self, **_):
            raise ConnectionError("redis is gone")

    app.state.statistics = Broken()
    try:
        assert board(client).status_code == 200
    finally:
        app.state.statistics = None


def test_the_day_after_boils_the_clients_down_to_a_summary():
    server = fakeredis.FakeServer()
    redis = fakeredis.FakeRedis(server=server, decode_responses=True)
    stats = statistics.Statistics(fakeredis.FakeAsyncRedis(server=server, decode_responses=True))
    now = datetime.now(ZONE)
    yesterday = now - timedelta(days=1)
    day = yesterday.strftime("%Y-%m-%d")

    async def run():
        for ip, times in (("192.0.2.1", 3), ("192.0.2.2", 1)):
            for _ in range(times):
                await stats.record(
                    path="/v1/stationboard",
                    query="station=Bern",
                    status=200,
                    exception=None,
                    client_ip=ip,
                    user_agent=None,
                    now=yesterday,
                )
        stats._rolled_over = None
        await stats.record(
            path="/v1/",
            query="",
            status=200,
            exception=None,
            client_ip="192.0.2.3",
            user_agent=None,
            now=now,
        )

    asyncio.run(run())

    assert not redis.exists(f"stats:clients:{day}")
    assert redis.hgetall(f"stats:clients:summary:{day}") == {
        "clients": "2",
        "requests": "4",
        "half": "1",
        "ninety": "2",
        "top10": "4",
    }


def test_summarise_finds_how_few_make_half():
    summary = statistics.summarise([50, 30, 10, 5, 5])

    assert summary == {"clients": 5, "requests": 100, "half": 1, "ninety": 3, "top10": 100}
