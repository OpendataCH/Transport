"""The backfill of AI clients from the access logs (tools/backfill_ai_clients.py)."""

import importlib.util
import json
from datetime import UTC, datetime
from pathlib import Path

import fakeredis
import pytest

spec = importlib.util.spec_from_file_location(
    "backfill_ai_clients", Path(__file__).parent.parent / "tools" / "backfill_ai_clients.py"
)
backfill = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backfill)

LINES = [
    # Claude Code, 21:41 UTC = 23 o'clock in Zurich, counted as other before.
    '1.2.3.4 - - [16/Oct/2026:21:41:36 +0000] "GET /v1/stationboard?station=Bern HTTP/1.1" '
    '200 10 "-" "Claude-User (claude-code/2.1.295; +https://support.anthropic.com/)" 0.1 0.1',
    # A browser app built in Lovable, known by its referer.
    '1.2.3.5 - - [16/Oct/2026:21:42:00 +0000] "GET /v1/connections?from=A&to=B HTTP/1.1" '
    '200 10 "https://zipsuche.lovable.app/" "Mozilla/5.0 (X11; Linux x86_64)" 0.1 0.1',
    # Nine's format: local time with an offset, no timings.
    '1.2.3.6 - - [16/Oct/2026:23:43:00 +0200] "GET /v1/locations?query=Bern HTTP/1.1" '
    '200 10 "-" "mcp-swiss/0.1.0"',
    # Not the API, not an AI, the health check: none of them count.
    '1.2.3.7 - - [16/Oct/2026:21:44:00 +0000] "GET /docs.html HTTP/1.1" 200 10 "-" "GPTBot/1.0"',
    '1.2.3.8 - - [16/Oct/2026:21:44:00 +0000] "GET /v1/locations HTTP/1.1" 200 10 "-" "curl/8"',
    '1.2.3.9 - - [16/Oct/2026:21:44:00 +0000] "GET /v1/health HTTP/1.1" 200 10 "-" "ClaudeBot"',
    # After the release: the service counts it itself.
    '1.2.3.4 - - [16/Oct/2026:22:00:00 +0000] "GET /v1/stationboard?station=Bern HTTP/1.1" '
    '200 10 "-" "Claude-User (claude-code/2.1.295; +https://support.anthropic.com/)" 0.1 0.1',
]


def test_scan_moves_each_ai_request_from_its_old_kind():
    moves = backfill.scan(iter(LINES), until=datetime(2026, 10, 16, 22, tzinfo=UTC), since=None)

    assert moves == {
        "2026-10-16T23": {
            "ai:Claude Code": 1,
            "client:ai-agent": 3,
            "client:other": -2,
            "ai:App in Lovable": 1,
            "client:browser": -1,
            "ai:MCP server": 1,
        }
    }


def test_apply_writes_once_and_never_below_zero(tmp_path, monkeypatch, capsys):
    server = fakeredis.FakeServer()
    redis = fakeredis.FakeRedis(server=server, decode_responses=True)
    monkeypatch.setattr(
        "redis.Redis.from_url",
        lambda *_, **__: fakeredis.FakeRedis(server=server, decode_responses=True),
    )
    redis.hset("stats:hourly:2026-10-16T23", mapping={"calls": 9, "client:script": 5})
    moves = tmp_path / "moves.json"
    moves.write_text(
        json.dumps(
            {
                "2026-10-16T23": {"ai:Claude Code": 7, "client:ai-agent": 7, "client:script": -7},
                "2026-10-16T22": {"ai:Claude Code": 1, "client:ai-agent": 1, "client:other": -1},
            }
        )
    )

    backfill.apply([str(moves)], "redis://", write=False)
    assert redis.hget("stats:hourly:2026-10-16T23", "ai:Claude Code") is None

    backfill.apply([str(moves)], "redis://", write=True)
    assert redis.hgetall("stats:hourly:2026-10-16T23") == {
        "calls": "9",
        "client:script": "0",
        "client:ai-agent": "7",
        "ai:Claude Code": "7",
    }
    # An hour nobody recorded stays unrecorded.
    assert not redis.exists("stats:hourly:2026-10-16T22")
    assert "2 requests not taken" in capsys.readouterr().err

    with pytest.raises(SystemExit):
        backfill.apply([str(moves)], "redis://", write=True)
