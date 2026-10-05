"""Smoke test of a running transport.opendata.ch: is it up, and is it the right one.

    python tools/smoke.py https://transport.opendata.ch
    python tools/smoke.py http://transport:8000 --version 2cb5db51 --no-redis

Checks what breaks silently rather than what the unit tests already cover: the
build and timezone the host reports, the website files, the statistics page in
its shapes, the error envelope, and one real question to search.ch. Standard
library only, so it runs in any Python image, in CI and on a laptop.

One request goes to search.ch through the API. A `429` there is accepted: it is
search.ch throttling the caller, and it still proves the path through the
service works and answers in the /v1 envelope.

Exits non-zero if any check fails, and says which.
"""

import argparse
import json
import sys
import time
import urllib.error
import urllib.request

TIMEOUT = 30


class Response:
    def __init__(self, status: int, headers, body: bytes) -> None:
        self.status = status
        self.headers = headers
        self.body = body

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", "replace")

    def json(self):
        return json.loads(self.body)


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


OPENER = urllib.request.build_opener(NoRedirect)


def get(base: str, path: str, method: str = "GET") -> Response:
    request = urllib.request.Request(
        base + path, method=method, headers={"User-Agent": "transport-smoke"}
    )
    try:
        with OPENER.open(request, timeout=TIMEOUT) as answer:
            return Response(answer.status, answer.headers, answer.read())
    except urllib.error.HTTPError as error:
        return Response(error.code, error.headers, error.read())


def wait_until_up(base: str, seconds: int) -> None:
    """A freshly started container needs a moment; give it that, no more."""
    deadline = time.monotonic() + seconds
    while True:
        try:
            if get(base, "/v1/health").status == 200:
                return
        except OSError:
            pass
        if time.monotonic() > deadline:
            raise SystemExit(f"{base} did not come up within {seconds} s")
        time.sleep(1)


def checks(base: str, version: str | None, redis: bool):
    """(name, function) pairs; each function raises AssertionError on failure."""

    def health():
        body = get(base, "/v1/health").json()
        assert body["status"] == "ok", body
        assert body["timezone"] == "Europe/Zurich", body
        # The offset is the point: a container on UTC would still say "ok".
        assert body["time"][-6:] in ("+01:00", "+02:00"), body["time"]
        if version:
            assert body["version"] == version, f"{body['version']} is running, not {version}"

    def api_info():
        body = get(base, "/v1/").json()
        assert body["version"] == "1.0" and body["author"] == "Opendata.ch", body

    def website():
        pages = ("/", "/docs.html", "/privacy.html", "/examples/", "/showcase.html", "/robots.txt")
        for path in pages:
            answer = get(base, path)
            assert answer.status == 200, f"{path}: {answer.status}"
        assert "Transport" in get(base, "/").text

    def swagger():
        document = get(base, "/swagger.json").json()
        assert document["swagger"] == "2.0", document.get("swagger")

    def head():
        assert get(base, "/docs.html", method="HEAD").status == 200

    def redirects():
        answer = get(base, "/examples")
        assert answer.status == 301 and answer.headers["location"] == "/examples/", answer.status
        answer = get(base, "/examples/connections.php?from=Bern")
        assert answer.status == 301, answer.status
        assert answer.headers["location"].endswith("connections.html?from=Bern")

    def not_found():
        answer = get(base, "/does-not-exist")
        assert answer.status == 404, answer.status
        assert answer.json() == {
            "errors": [{"message": 'No route found for "GET /does-not-exist"'}]
        }

    def statistics():
        for path in ("/stats", "/stats.php"):
            page = get(base, path)
            assert page.status == 200, f"{path}: {page.status}"
            if not redis:
                assert "No Redis configured" in page.text, page.text[:80]
                continue
            assert 'id="error-details"' in page.text, f"{path}: not the statistics page"
            data = get(base, path + "?format=json").json()["data"]
            # Keys, not values: a staging Redis has a history of days, not of years.
            assert data and set(data[0]) == {"date", "calls", "errors"}, data[:1]
            csv = get(base, path + "?format=csv")
            assert csv.text.startswith("Date,Calls,Errors\n"), csv.text[:40]
            window = get(base, path + "?format=window&window=24h").json()
            assert window["window"] == "24h" and window["granularity"] == "hour", window.keys()

    def search_ch():
        answer = get(base, "/v1/locations?query=Bern")
        if answer.status == 429:
            message = answer.json()["errors"][0]["message"]
            assert "timetable.search.ch" in message, message
            return
        assert answer.status == 200, f"{answer.status}: {answer.text[:200]}"
        stations = answer.json()["stations"]
        assert any(s["name"] == "Bern" for s in stations), stations[:3]

    return [
        ("health: build and timezone", health),
        ("/v1/ says what it is", api_info),
        ("website pages", website),
        ("/swagger.json", swagger),
        ("HEAD like GET", head),
        ("redirects", redirects),
        ("404 in the error envelope", not_found),
        ("statistics page, both names", statistics),
        ("one question to search.ch", search_ch),
    ]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("base", help="e.g. https://transport.opendata.ch")
    parser.add_argument("--version", help="the build /v1/health must report")
    parser.add_argument("--no-redis", action="store_true", help="the host runs without statistics")
    parser.add_argument("--wait", type=int, default=60, help="seconds to wait for health")
    args = parser.parse_args()
    base = args.base.rstrip("/")

    wait_until_up(base, args.wait)
    failed = 0
    for name, check in checks(base, args.version, not args.no_redis):
        try:
            check()
            print(f"ok    {name}")
        except Exception as error:  # noqa: BLE001 - every failure is reported, not raised
            failed += 1
            print(f"FAIL  {name}: {error}")
    print(
        f"{failed} of {len(checks(base, None, True))} checks failed"
        if failed
        else "all checks passed"
    )
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
