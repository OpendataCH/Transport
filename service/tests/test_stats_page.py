"""/stats.php, read from the keys the PHP application and this service write."""

from datetime import datetime, timedelta

import fakeredis
import pytest

from transport_api import statistics, stats_page
from transport_api.main import app

ZONE = statistics.ZONE


@pytest.fixture
def redis():
    server = fakeredis.FakeServer()
    app.state.statistics = statistics.Statistics(
        fakeredis.FakeAsyncRedis(server=server, decode_responses=True)
    )
    yield fakeredis.FakeRedis(server=server, decode_responses=True)
    app.state.statistics = None


def day(redis, date: str, calls: int, errors: int = 0) -> None:
    redis.sadd("stats:calls", f"stats:calls:{date}")
    redis.set(f"stats:calls:{date}", calls)
    if errors:
        redis.sadd("stats:errors", f"stats:errors:{date}")
        redis.set(f"stats:errors:{date}", errors)


def test_without_redis_the_page_says_so(client):
    assert "No Redis configured" in client.get("/stats.php").text


def test_json_is_calls_and_errors_per_day(client, redis):
    day(redis, "2012-03-30", 4)
    day(redis, "2012-03-31", 3766, errors=2)

    response = client.get("/stats.php", params={"format": "json"})

    assert response.headers["content-type"] == "application/json"
    assert response.content == (
        b'{"data":[{"date":"2012-03-30","calls":4,"errors":0},'
        b'{"date":"2012-03-31","calls":3766,"errors":2}]}'
    )


def test_csv_has_no_trailing_newline(client, redis):
    day(redis, "2012-03-30", 4)
    day(redis, "2012-03-31", 3766, errors=2)

    response = client.get("/stats.php", params={"format": "csv"})

    assert response.headers["content-type"] == "text/csv; charset=utf-8"
    assert response.headers["content-disposition"] == "attachment;filename=transport.csv"
    assert response.text == "Date,Calls,Errors\n2012-03-30,4,0\n2012-03-31,3766,2"


def test_the_page_renders_the_totals(client, redis):
    day(redis, "2012-03-30", 1000)
    day(redis, "2012-03-31", 2001)
    redis.hset("stats:resources:/v1/connections", mapping={"path": "/v1/connections", "calls": 7})
    redis.sadd("stats:resources", "stats:resources:/v1/connections")

    page = client.get("/stats.php")

    assert page.status_code == 200
    assert page.headers["content-type"].startswith("text/html")
    assert "3&#39;001" in page.text or "3'001" in page.text
    assert "1'501" in page.text or "1&#39;501" in page.text  # the average, rounded half up
    assert "/v1/connections" in page.text


def test_an_hour_window_reads_the_hourly_buckets(client, redis):
    now = datetime.now(ZONE)
    hour = f"stats:hourly:{now:%Y-%m-%dT%H}"
    redis.hset(
        hour,
        mapping={
            "calls": 90,
            "errors": 3,
            "ratelimited": 10,
            "exception:Buzz\\Exception\\RequestException": 2,
            "exception:Exception": 1,
            "client:homeassistant": 60,
            "client:browser": 40,
        },
    )
    redis.zadd(f"stats:top:stations:{now:%Y-%m-%d}", {"Bern": 5, "8507000": 2})

    data = client.get("/stats.php", params={"format": "window", "window": "1h"}).json()

    assert data["granularity"] == "hour"
    assert (data["calls"], data["errors"], data["ratelimited"]) == (90, 3, 10)
    assert [e["name"] for e in data["exceptions"]] == ["RequestException", "Exception"]
    assert data["exceptions"][0]["status"] == "500"
    assert data["clientKinds"][0] == {
        "kind": "homeassistant",
        "label": "Home Assistant",
        "requests": 60,
        "share": 60,
    }
    assert data["stations"] == [
        {"name": "Bern", "requests": 5},
        {"name": "8507000", "requests": 2},
    ]
    assert data["profile"][now.hour] == 100


def test_an_unknown_window_is_the_last_day(client, redis):
    data = client.get("/stats.php", params={"format": "window", "window": "1y"}).json()

    assert data["window"] == "24h"
    assert data["since"] is None
    assert data["ratelimited"] is None


def test_a_day_window_joins_the_daily_counters_and_the_buckets(client, redis):
    now = datetime.now(ZONE)
    yesterday = (now - timedelta(days=1)).date().isoformat()
    day(redis, yesterday, 500, errors=5)
    redis.hset(f"stats:hourly:{yesterday}T12", mapping={"calls": 1, "ratelimited": 7})
    redis.zadd(f"stats:top:routes:{yesterday}", {"Bern → Zug": 3})
    redis.zadd(f"stats:top:routes:{now:%Y-%m-%d}", {"Bern → Zug": 1, "Basel → Olten": 2})
    redis.hset(
        f"stats:clients:summary:{yesterday}",
        mapping={"clients": 10, "requests": 500, "half": 2, "ninety": 6, "top10": 500},
    )

    data = client.get("/stats.php", params={"format": "window", "window": "7d"}).json()

    assert data["granularity"] == "day"
    assert data["rows"][1] == {"start": yesterday, "calls": 500, "errors": 5, "ratelimited": 7}
    assert data["routes"] == [
        {"name": "Bern → Zug", "requests": 4},
        {"name": "Basel → Olten", "requests": 2},
    ]
    assert data["clientDays"] == [
        {"date": yesterday, "clients": 10, "requests": 500, "half": 2, "ninety": 6, "top10": 500}
    ]


def test_the_places_name_the_calendar_days_they_cover(client, redis):
    now = datetime.now(ZONE)
    two_days_ago = (now - timedelta(days=2)).date().isoformat()
    redis.zadd(f"stats:top:stations:{two_days_ago}", {"Bern": 3})
    redis.zadd(f"stats:top:routes:{now:%Y-%m-%d}", {"Bern → Zug": 1})

    data = client.get("/stats.php", params={"format": "window", "window": "7d"}).json()

    assert data["placesDays"] == {"from": two_days_ago, "to": f"{now:%Y-%m-%d}", "untilNow": True}


def test_an_hour_window_shows_the_whole_day_of_places(client, redis):
    now = datetime.now(ZONE)
    redis.zadd(f"stats:top:stations:{now:%Y-%m-%d}", {"Bern": 3})

    data = client.get("/stats.php", params={"format": "window", "window": "1h"}).json()

    assert data["granularity"] == "hour"
    assert data["placesDays"]["from"] == data["placesDays"]["to"] == f"{now:%Y-%m-%d}"


def test_without_counted_places_there_are_no_days(client, redis):
    data = client.get("/stats.php", params={"format": "window", "window": "7d"}).json()

    assert data["placesDays"] is None


def test_the_window_json_is_escaped_as_symfony_escapes_it(client, redis):
    now = datetime.now(ZONE)
    redis.zadd(f"stats:top:routes:{now:%Y-%m-%d}", {"Bern → Zug": 1})

    raw = client.get("/stats.php", params={"format": "window", "window": "1h"}).content

    assert b"Bern \\u2192 Zug" in raw
    assert b'"label":"Last hour"' in raw


def test_the_statistics_page_is_not_counted(client, redis):
    client.get("/stats.php", params={"format": "json"})

    assert redis.keys("stats:hourly:*") == []


@pytest.mark.parametrize(
    ("value", "text"), [(0, "0"), (999, "999"), (1500.5, "1'501"), (4737639, "4'737'639")]
)
def test_numbers_are_formatted_as_twig_formats_them(value, text):
    assert stats_page.number(value) == text


def test_shares_are_integers_when_they_divide_evenly():
    assert stats_page._share(1, 4) == 25
    assert isinstance(stats_page._share(1, 4), int)
    assert stats_page._share(1, 3) == 100 / 3
