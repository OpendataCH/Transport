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
    ("upstream_status", "expected"),
    [(429, 429), (500, 500), (503, 500)],
)
def test_upstream_status_codes_are_mapped_as_v1_maps_them(
    client, search_ch, upstream_status, expected
):
    """A 429 is passed through; it is the caller's to retry, and 8.3 % of
    production traffic on /v1 is exactly this. Anything else the upstream does
    wrong is a 500 whose message names search.ch - which is what /v1 answers,
    and /v2 is the same API.
    """
    search_ch.returns_text("no", status_code=upstream_status)

    response = client.get("/v2/locations", params={"query": "Be"})

    assert response.status_code == expected
    assert "timetable.search.ch" in response.json()["errors"][0]["message"]


def test_the_error_envelope_is_the_one_v1_uses(client, search_ch):
    search_ch.returns_text("slow down", status_code=429)

    body = client.get("/v2/locations", params={"query": "Be"}).json()

    assert body == {"errors": [{"message": "Rate limit error from timetable.search.ch: slow down"}]}


def test_a_timeout_does_not_hold_the_request_open(client, search_ch):
    """/v1 sets no timeout at all and waits as long as the socket does."""
    search_ch.raises(httpx.ReadTimeout("too slow"))

    assert client.get("/v2/locations", params={"query": "Be"}).status_code == 500


def test_a_broken_connection_is_reported_as_a_server_error(client, search_ch):
    search_ch.raises(httpx.ConnectError("refused"))

    assert client.get("/v2/locations", params={"query": "Be"}).status_code == 500


def test_something_that_is_not_json_says_so(client, search_ch):
    search_ch.returns_text("<html>maintenance</html>")

    body = client.get("/v2/locations", params={"query": "Be"}).json()

    assert "Invalid JSON from timetable.search.ch" in body["errors"][0]["message"]


def test_an_error_reported_inside_a_200_is_still_an_error(client, search_ch):
    """search.ch reports some failures in the body of a perfectly good 200."""
    search_ch.returns({"error": "unknown parameter"})

    response = client.get("/v2/locations", params={"query": "Be"})

    assert response.status_code == 500
    assert "unknown parameter" in response.json()["errors"][0]["message"]


def test_an_answer_of_the_wrong_shape_is_a_server_error(client, search_ch):
    search_ch.returns({"stations": []})

    assert client.get("/v2/locations", params={"query": "Be"}).status_code == 500
