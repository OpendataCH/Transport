#!/usr/bin/env python3
"""Count the AI clients of the past into the hourly buckets, from the access logs.

The service counts AI clients by name since the release that introduced them
(`statistics.AI_CLIENTS`). The hours before that already have their buckets, with
the AI requests filed under browser, script or other. This moves them: for every
AI request in the log it adds `ai:<name>` and `client:<ai kind>` and takes one
from the kind the request was counted as before, so the kinds still add up.

Two steps, because the logs and Redis live on different hosts:

    # per log, the moves per hour (UTC or any offset in the log, Zurich hours out)
    ssh OPEN-PRD 'docker exec transport-access-log-1 sh -c "zcat /logs/*.gz"' \\
        | python tools/backfill_ai_clients.py scan --until 2026-10-17T08:00:00Z > prd.json
    ssh OPEN-NINE 'zstdcat ~/logs/transport.opendata.ch.access.log-202609*.zst' \\
        | python tools/backfill_ai_clients.py scan --until 2026-10-05T11:40:00Z > nine.json

    # once, into Redis (dry run without --apply)
    python tools/backfill_ai_clients.py apply prd.json nine.json --redis redis://localhost:16379

`--until` is the moment the release that counts AI clients went live (or, for a
host that stopped serving, the moment it stopped counting into these buckets):
from then on the service counts them itself. `apply` only touches buckets that
exist - an hour nobody recorded stays unrecorded - never takes a kind below
zero, and refuses to run twice (`stats:backfill:ai`).

Only what the service counts is counted: the API paths, without the health
checks. The Referer stands in for the Origin, which the log does not keep.
"""

import argparse
import json
import sys
from collections import defaultdict
from datetime import UTC, datetime
from functools import cache, lru_cache
from pathlib import Path
from urllib.parse import urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from transport_api.statistics import (  # noqa: E402
    HOURLY_TTL,
    UNCOUNTED,
    ZONE,
    ai_client,
    plain_kind,
)

FLAG = "stats:backfill:ai"


@cache
def _by_agent(user_agent: str) -> tuple[str, str] | None:
    return ai_client(user_agent)


@lru_cache(maxsize=100_000)
def _by_origin(referer: str) -> tuple[str, str] | None:
    host = urlsplit(referer).netloc
    return ai_client(None, host) if host else None


@cache
def _plain(user_agent: str) -> str:
    return plain_kind(user_agent)


@lru_cache(maxsize=10_000)
def _hour(stamp: str) -> tuple[str, datetime]:
    """The Zurich hour of a log time stamp cut to the hour, e.g. 16/Oct/2026:21 +0000."""
    start = datetime.strptime(stamp, "%d/%b/%Y:%H %z")
    return f"{start.astimezone(ZONE):%Y-%m-%dT%H}", start


def scan(lines, until: datetime | None, since: datetime | None) -> dict[str, dict[str, int]]:
    moves: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for line in lines:
        parts = line.split('"')
        if len(parts) < 6:
            continue
        request = parts[1].split(" ")
        if len(request) < 2:
            continue
        path = request[1].split("?", 1)[0]
        if not path.startswith(("/v1", "/v2")) or path in UNCOUNTED:
            continue
        user_agent = parts[5]
        referer = parts[3]
        ai = _by_agent(user_agent)
        if ai is None and referer not in ("", "-"):
            ai = _by_origin(referer)
        if ai is None:
            continue

        head = parts[0]
        open_at = head.find("[")
        stamp = head[open_at + 1 : head.find("]", open_at)]  # 16/Oct/2026:21:41:36 +0000
        hour, start = _hour(f"{stamp[:14]} {stamp[-5:]}")
        if until is not None or since is not None:
            at = datetime.strptime(stamp, "%d/%b/%Y:%H:%M:%S %z")
            if (until is not None and at >= until) or (since is not None and at < since):
                continue

        name, kind = ai
        bucket = moves[hour]
        bucket[f"ai:{name}"] += 1
        bucket[f"client:{kind}"] += 1
        bucket[f"client:{_plain(user_agent)}"] -= 1
    return {hour: dict(fields) for hour, fields in sorted(moves.items())}


def _merged(paths: list[str]) -> dict[str, dict[str, int]]:
    total: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for path in paths:
        for hour, fields in json.loads(Path(path).read_text()).items():
            for field, delta in fields.items():
                total[hour][field] += delta
    return total


def apply(paths: list[str], url: str, write: bool) -> None:
    import redis

    client = redis.Redis.from_url(url, decode_responses=True)
    if client.exists(FLAG):
        sys.exit(f"already backfilled: {client.get(FLAG)}")

    moves = _merged(paths)
    missing, clamped, requests = [], 0, 0
    pipe = client.pipeline(transaction=False)
    for hour, fields in sorted(moves.items()):
        key = f"stats:hourly:{hour}"
        current = client.hgetall(key)
        if not current:
            missing.append(hour)
            continue
        for field, delta in fields.items():
            if delta < 0:
                have = int(current.get(field, 0))
                if have < -delta:
                    clamped += -delta - have
                delta = -min(have, -delta)
            elif field.startswith("ai:"):
                requests += delta
            if delta:
                pipe.hincrby(key, field, delta)
        if client.ttl(key) < 0:
            pipe.expire(key, HOURLY_TTL)

    print(f"{len(moves)} hours, {requests} AI requests moved", file=sys.stderr)
    if missing:
        print(
            f"{len(missing)} hours without a bucket skipped: {missing[0]} … {missing[-1]}",
            file=sys.stderr,
        )
    if clamped:
        print(f"{clamped} requests not taken from a kind that had fewer", file=sys.stderr)
    if not write:
        print("dry run - nothing written (--apply writes)", file=sys.stderr)
        return
    pipe.set(FLAG, f"{datetime.now(UTC):%Y-%m-%dT%H:%M:%SZ} {' '.join(paths)}")
    pipe.execute()
    print("written", file=sys.stderr)


def _instant(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    commands = parser.add_subparsers(dest="command", required=True)
    scan_cmd = commands.add_parser("scan", help="moves per hour from a log on stdin, as JSON")
    scan_cmd.add_argument("--until", help="ignore requests from this instant on (ISO 8601)")
    scan_cmd.add_argument("--since", help="ignore requests before this instant (ISO 8601)")
    apply_cmd = commands.add_parser("apply", help="write the moves into Redis, once")
    apply_cmd.add_argument("files", nargs="+")
    apply_cmd.add_argument("--redis", required=True)
    apply_cmd.add_argument("--apply", action="store_true", help="write; without it a dry run")
    args = parser.parse_args()

    if args.command == "scan":
        lines = (line for line in sys.stdin.buffer)
        decoded = (line.decode("utf-8", "replace") for line in lines)
        json.dump(scan(decoded, _instant(args.until), _instant(args.since)), sys.stdout)
    else:
        apply(args.files, args.redis, args.apply)


if __name__ == "__main__":
    main()
