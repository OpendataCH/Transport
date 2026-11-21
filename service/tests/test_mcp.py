"""The MCP server at /mcp: the protocol, the tools, and what /stats sees of them."""

from datetime import datetime

import fakeredis
import pytest
from conftest import station
from fastapi.testclient import TestClient

from transport_api import mcp_server, statistics
from transport_api.main import app

ZONE = statistics.ZONE
HEADERS = {"accept": "application/json, text/event-stream", "user-agent": "Claude-User/1.0"}


@pytest.fixture
def mcp_client(timetable):
    """A client with the lifespan running: the session manager lives there."""
    with TestClient(app) as client:
        yield client


@pytest.fixture
def redis(mcp_client):
    # After the lifespan, which sets the statistics to None without REDIS_URL.
    server = fakeredis.FakeServer()
    app.state.statistics = statistics.Statistics(
        fakeredis.FakeAsyncRedis(server=server, decode_responses=True)
    )
    yield fakeredis.FakeRedis(server=server, decode_responses=True)
    app.state.statistics = None


def rpc(client, method: str, params: dict | None = None, **headers):
    response = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}},
        headers={**HEADERS, **headers},
    )
    assert response.status_code == 200, response.text
    return response.json()


def call(client, tool: str, arguments: dict, **headers) -> str:
    body = rpc(client, "tools/call", {"name": tool, "arguments": arguments}, **headers)
    assert "result" in body, body
    return body["result"]["content"][0]["text"]


def test_initialize_names_the_server(mcp_client):
    body = rpc(
        mcp_client,
        "initialize",
        {
            "protocolVersion": "2025-06-18",
            "capabilities": {},
            "clientInfo": {"name": "test", "version": "1"},
        },
    )
    info = body["result"]["serverInfo"]
    assert info["name"] == "transport.opendata.ch"
    assert "Swiss" in body["result"]["instructions"]


def test_the_tools_are_listed_as_read_only(mcp_client):
    tools = {t["name"]: t for t in rpc(mcp_client, "tools/list")["result"]["tools"]}
    assert set(tools) == {"find_stations", "stations_nearby", "connections", "departures"}
    for tool in tools.values():
        assert tool["annotations"]["readOnlyHint"] is True
        assert "ctx" not in tool["inputSchema"].get("properties", {})


def test_find_stations_answers_from_v1(mcp_client, timetable):
    timetable.returns([station("8507000", "Bern", 46.948831, 7.439129, icon="train")])
    text = call(mcp_client, "find_stations", {"query": "Bern"})
    assert text == "- Bern (id 8507000, train)"
    assert timetable.queries == ["Bern"]


def test_nothing_found_is_said_in_words(mcp_client, timetable):
    assert call(mcp_client, "find_stations", {"query": "Xyz"}) == "No station found for 'Xyz'."


def test_a_tool_call_is_counted_as_the_mcp_and_the_protocol_is_not(mcp_client, timetable, redis):
    timetable.returns([station("8507000", "Bern", 46.948831, 7.439129)])
    rpc(mcp_client, "tools/list")
    call(mcp_client, "find_stations", {"query": "Bern"})

    hour = "stats:hourly:" + datetime.now(ZONE).strftime("%Y-%m-%dT%H")
    assert redis.hget(hour, "calls") == "1"
    assert redis.hget(hour, "ai:transport.opendata.ch MCP") == "1"
    assert redis.hgetall("stats:resources:/v1/locations")["calls"] == "1"
    assert not redis.exists("stats:resources:/mcp")


def test_the_callers_address_is_passed_on(mcp_client, timetable, redis):
    timetable.returns([station("8507000", "Bern", 46.948831, 7.439129)])
    call(mcp_client, "find_stations", {"query": "Bern"}, **{"x-forwarded-for": "203.0.113.7"})
    call(mcp_client, "find_stations", {"query": "Bern"}, **{"x-forwarded-for": "198.51.100.9"})

    clients = redis.zrange(f"stats:clients:{datetime.now(ZONE):%Y-%m-%d}", 0, -1)
    assert len(clients) == 2


CONNECTION = {
    "from": {"name": "Bern"},
    "to": {"name": "Zürich HB"},
    "connections": [
        {
            "from": {
                "station": {"name": "Bern"},
                "departure": "2026-11-21T16:31:00+0100",
                "delay": 4,
                "platform": "8",
                "prognosis": {"platform": None},
            },
            "to": {
                "station": {"name": "Zürich HB"},
                "arrival": "2026-11-21T17:28:00+0100",
                "delay": 0,
                "platform": "33",
            },
            "duration": "00d00:57:00",
            "transfers": 0,
            "sections": [
                {
                    "journey": {
                        "category": "IC",
                        "number": "1",
                        "to": "St. Gallen",
                        "operator": "SBB",
                    },
                    "walk": None,
                    "departure": {
                        "station": {"name": "Bern"},
                        "departure": "2026-11-21T16:31:00+0100",
                        "delay": 4,
                        "platform": "8",
                    },
                    "arrival": {
                        "station": {"name": "Zürich HB"},
                        "arrival": "2026-11-21T17:28:00+0100",
                        "platform": "33",
                    },
                },
                {
                    "journey": None,
                    "walk": {"duration": 240},
                    "departure": {"station": {"name": "Zürich HB"}},
                    "arrival": {"station": {"name": "Zürich, Bahnhofquai/HB"}},
                },
            ],
        }
    ],
}


def test_a_connection_is_a_few_lines(mcp_client, monkeypatch):
    asked = {}

    async def fake_get(path, params, ctx):
        asked["path"], asked["params"] = path, params
        return CONNECTION

    monkeypatch.setattr(mcp_server, "_get", fake_get)
    text = call(
        mcp_client,
        "connections",
        {"origin": "Bern", "destination": "Zürich", "time": "16:30", "via": ["Olten"]},
    )
    assert asked["path"] == "/v1/connections"
    assert ("time", "16:30") in asked["params"]
    assert ("via[]", "Olten") in asked["params"]
    assert text.splitlines() == [
        "Connections Bern → Zürich HB (times Swiss local, delays as +min):",
        "1. Sat 2026-11-21 16:31 Bern, platform 8, +4 min → 17:28 Zürich HB, platform 33"
        " · 57 min · direct",
        "   - IC 1 to St. Gallen (SBB): 16:31 Bern, platform 8, +4 min → 17:28 Zürich HB,"
        " platform 33",
        "   - walk 4 min to Zürich, Bahnhofquai/HB",
    ]


def test_an_error_of_v1_reaches_the_model(mcp_client, timetable):
    # The fake timetable finds no stop for a board: /v1 answers in its error envelope.
    text = call(mcp_client, "departures", {"station": "Nowhere"})
    assert text.startswith("Error: ") or text.startswith("No departures")


def test_durations():
    assert mcp_server._minutes("00d00:57:00") == "57 min"
    assert mcp_server._minutes("00d01:05:00") == "1 h 05 min"
    assert mcp_server._minutes("01d02:00:00") == "26 h 00 min"


def fake_v1(monkeypatch, answer=None, error=None):
    asked = {}

    async def fake_get(path, params, ctx):
        asked["path"], asked["params"] = path, params
        if error:
            raise mcp_server.ToolFailure(error)
        return answer

    monkeypatch.setattr(mcp_server, "_get", fake_get)
    return asked


def test_stations_nearby_gives_distances(mcp_client, monkeypatch):
    asked = fake_v1(
        monkeypatch,
        {
            "stations": [
                {"id": "8507000", "name": "Bern", "distance": 120},
                {"id": None, "name": "an address", "distance": 5},
            ]
        },
    )
    text = call(mcp_client, "stations_nearby", {"latitude": 46.95, "longitude": 7.44})
    assert asked["params"] == [("x", "46.95"), ("y", "7.44")]
    assert text == "- Bern (id 8507000), 120 m"


def test_stations_nearby_nothing_found(mcp_client, monkeypatch):
    fake_v1(monkeypatch, {"stations": []})
    assert call(mcp_client, "stations_nearby", {"latitude": 0, "longitude": 0}) == (
        "No stop found near that point."
    )


def test_departures_are_one_line_each(mcp_client, monkeypatch):
    asked = fake_v1(
        monkeypatch,
        {
            "station": {"name": "Bern"},
            "stationboard": [
                {
                    "category": "S",
                    "number": "6",
                    "to": "Schwarzenburg",
                    "operator": "BLS-bls",
                    "stop": {
                        "departure": "2026-11-21T16:06:00+0100",
                        "platform": "13D-F",
                        "delay": 2,
                        "prognosis": {"platform": None},
                    },
                },
                {"category": "IR", "number": "15", "to": "Luzern", "stop": {"arrival": None}},
            ],
        },
    )
    text = call(
        mcp_client,
        "departures",
        {"station": "Bern", "when": "2026-11-21 16:00", "arrivals": False, "limit": 2},
    )
    assert ("datetime", "2026-11-21 16:00") in asked["params"]
    assert text.splitlines() == [
        "Departures from Bern, Sat 2026-11-21:",
        "- 16:06 S 6 to Schwarzenburg (BLS-bls) · platform 13D-F, +2 min",
        "- ? IR 15 to Luzern",
    ]


def test_arrivals_are_asked_for_as_type_arrival(mcp_client, monkeypatch):
    asked = fake_v1(monkeypatch, {"station": {"name": "Bern"}, "stationboard": []})
    text = call(mcp_client, "departures", {"station": "Bern", "arrivals": True})
    assert ("type", "arrival") in asked["params"]
    assert text == "No arrivals found for 'Bern'."


@pytest.mark.parametrize(
    ("tool", "arguments"),
    [
        ("find_stations", {"query": "Bern"}),
        ("stations_nearby", {"latitude": 1, "longitude": 2}),
        ("connections", {"origin": "A", "destination": "B"}),
        ("departures", {"station": "Bern"}),
    ],
)
def test_a_failure_of_v1_is_told_to_the_model(mcp_client, monkeypatch, tool, arguments):
    fake_v1(monkeypatch, error="Timetable not available")
    body = rpc(mcp_client, "tools/call", {"name": tool, "arguments": arguments})
    assert body["result"]["isError"] is True
    assert body["result"]["content"][0]["text"].endswith(": Timetable not available")


def test_tools_answer_in_text_only_and_say_they_only_read(mcp_client, monkeypatch):
    tools = rpc(mcp_client, "tools/list", {})["result"]["tools"]
    for tool in tools:
        assert tool["title"]
        assert "outputSchema" not in tool
        assert tool["annotations"]["readOnlyHint"] is True
        assert tool["annotations"]["idempotentHint"] is True
    fake_v1(monkeypatch, {"stations": []})
    body = rpc(mcp_client, "tools/call", {"name": "find_stations", "arguments": {"query": "x"}})
    assert "structuredContent" not in body["result"]


@pytest.mark.parametrize(
    ("number", "label"),
    [("1", "IC 1"), ("000377", "ICE 377"), ("?", "ICE"), (None, "ICE")],
)
def test_a_line_is_named_without_padding_or_question_mark(number, label):
    category = "IC" if number == "1" else "ICE"
    assert mcp_server._line({"category": category, "number": number}) == label


def test_connections_with_arrival_time_and_changes(mcp_client, monkeypatch):
    answer = {
        "from": {"name": "A"},
        "to": {"name": "B"},
        "connections": [
            dict(CONNECTION["connections"][0], transfers=2, sections=[]),
        ],
    }
    asked = fake_v1(monkeypatch, answer)
    text = call(
        mcp_client,
        "connections",
        {"origin": "A", "destination": "B", "date": "2026-11-22", "arrive_by": True},
    )
    assert ("isArrivalTime", "1") in asked["params"]
    assert ("date", "2026-11-22") in asked["params"]
    assert text.splitlines()[1].endswith("· 2 changes")


def test_no_connection_is_said_in_words(mcp_client, monkeypatch):
    fake_v1(monkeypatch, {"connections": []})
    assert call(mcp_client, "connections", {"origin": "A", "destination": "B"}) == (
        "No connection found from 'A' to 'B'."
    )


def test_an_error_envelope_becomes_a_tool_failure(mcp_client, monkeypatch, timetable):
    # The real _get against the app: an unknown path is answered in the error envelope.
    with pytest.raises(mcp_server.ToolFailure):
        import asyncio

        asyncio.run(mcp_server._get("/v1/nowhere", [], None))


def test_a_browser_gets_the_page_on_adding_it(mcp_client):
    response = mcp_client.get("/mcp", headers={"accept": "text/html,*/*"})
    assert response.status_code == 200
    assert "https://transport.opendata.ch/mcp" in response.text
    assert "Add custom connector" in response.text
    assert 'href="/docs.html#mcp"' in response.text
