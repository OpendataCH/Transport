"""What is sent to search.ch, and what comes back when it says no.

Both halves are traps named in the plan. The forwarding one is the worse of the
two: when it breaks, search.ch throttles all our callers as one and the only
symptom is a rise in 429s.
"""

import httpx
import pytest


def test_the_caller_is_who_search_ch_sees(client, search_ch):
    """Not this server, and not the nginx in front of it."""
    client.get(
        "/v2/locations",
        params={"query": "Be"},
        headers={
            "X-Forwarded-For": "203.0.113.5, 198.51.100.7",
            "User-Agent": "HomeAssistant/2026.9",
        },
    )

    sent = search_ch.last.url.params
    assert sent["ip_address"] == "203.0.113.5"
    assert sent["user_agent"] == "HomeAssistant/2026.9"


def test_a_key_is_forwarded_unchanged(client, search_ch):
    client.get("/v2/locations", params={"query": "Be", "key": "abc123"})

    assert search_ch.last.url.params["key"] == "abc123"


def test_without_a_key_none_is_invented(client, search_ch):
    client.get("/v2/locations", params={"query": "Be"})

    assert "key" not in search_ch.last.url.params


@pytest.mark.parametrize(
    ("upstream_status", "expected", "kind"),
    [
        (429, 429, "upstream-rate-limited"),
        (500, 502, "upstream-failed"),
        (503, 502, "upstream-failed"),
    ],
)
def test_upstream_status_codes_are_mapped(client, search_ch, upstream_status, expected, kind):
    """A 429 stays a 429 - it is the caller's to retry.

    A fault of search.ch becomes 502, never 500: 500 would claim the fault is
    here, and whoever is paged would look in the wrong place.
    """
    search_ch.returns_text("no", status_code=upstream_status)

    response = client.get("/v2/locations", params={"query": "Be"})

    assert response.status_code == expected
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"].endswith("/" + kind)


def test_a_timeout_is_a_gateway_timeout(client, search_ch):
    search_ch.raises(httpx.ReadTimeout("too slow"))

    response = client.get("/v2/locations", params={"query": "Be"})

    assert response.status_code == 504
    assert response.json()["type"].endswith("/upstream-timeout")


def test_a_broken_connection_is_a_bad_gateway(client, search_ch):
    search_ch.raises(httpx.ConnectError("refused"))

    assert client.get("/v2/locations", params={"query": "Be"}).status_code == 502


def test_something_that_is_not_json_is_a_bad_gateway(client, search_ch):
    search_ch.returns_text("<html>maintenance</html>")

    assert client.get("/v2/locations", params={"query": "Be"}).status_code == 502


def test_an_error_reported_inside_a_200_is_still_an_error(client, search_ch):
    """search.ch reports some failures in the body of a perfectly good 200."""
    search_ch.returns({"error": "unknown parameter"})

    response = client.get("/v2/locations", params={"query": "Be"})

    assert response.status_code == 502
    assert "unknown parameter" in response.json()["detail"]


def test_an_answer_of_the_wrong_shape_is_a_bad_gateway(client, search_ch):
    search_ch.returns({"stations": []})

    assert client.get("/v2/locations", params={"query": "Be"}).status_code == 502
