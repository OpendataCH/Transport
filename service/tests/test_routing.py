"""What this service answers, and what it leaves alone.

Until stage S6 the rule here was the opposite one: the service refused the
whole `/v1` surface, so that a location block written too broadly could not
shadow the old contract with a half-built answer. S6 is the deliberate end of
that guard - `/v1` is now this service's own prefix, `/v2` is an alias of it,
and the PHP application answers on `/v1-old` while the two are compared.

What has *not* changed is the other half: the website around the API is not
served here.
"""

import pytest

PREFIXES = ["/v1", "/v2"]


@pytest.mark.parametrize("prefix", PREFIXES)
def test_both_prefixes_answer(client, prefix):
    assert client.get(f"{prefix}/health").json()["status"] == "ok"


def test_the_two_prefixes_are_the_same_routes(client, search_ch):
    """An alias, not a second version."""
    search_ch.returns([{"label": "Bern", "id": "8507000", "iconclass": "sl-icon-type-train"}])

    assert (
        client.get("/v1/locations", params={"query": "Bern"}).json()
        == client.get("/v2/locations", params={"query": "Bern"}).json()
    )


def test_the_api_version_is_the_one_the_prefix_promises(client):
    """`/v1/` has always said 1.0, and its answer is compared byte for byte."""
    assert client.get("/v1/").json()["version"] == "1.0"
    assert client.get("/v2/").json()["version"] == "2.0"


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/docs.html",
        "/showcase.html",
        "/examples/",
        "/swagger.json",
        "/stats",
        "/robots.txt",
    ],
)
def test_the_website_around_the_api_is_not_served_here(client, path):
    """It comes from the PHP container, and still has to on the day of the flip."""
    assert client.get(path).status_code == 404


def test_the_v1_old_prefix_belongs_to_the_other_implementation(client):
    """nginx sends it to PHP; nothing here may answer it."""
    assert client.get("/v1-old/locations").status_code == 404


def test_the_documents_live_under_the_documented_prefix(client):
    assert client.get("/openapi.json").status_code == 404

    document = client.get("/v1/openapi.json")
    assert document.status_code == 200
    # FastAPI emits OpenAPI 3.1; the PHP application generates a Swagger 2.0
    # document at /swagger.json. Two documents, two addresses, on purpose.
    assert document.json()["openapi"].startswith("3.1")

    paths = document.json()["paths"]
    # The alias is mounted but not described: a client reading this should see
    # one API, not two names for it.
    assert all(path.startswith("/v1/") for path in paths), sorted(paths)
    assert {"/v1/", "/v1/locations", "/v1/stationboard", "/v1/connections"} <= set(paths)


@pytest.mark.parametrize("prefix", PREFIXES)
def test_both_human_readable_documents_are_served(client, prefix):
    """Swagger UI at `docs`, ReDoc at `documentation`, under either prefix."""
    assert client.get(f"{prefix}/docs").status_code == 200
    assert client.get(f"{prefix}/documentation").status_code == 200
    assert client.get(f"{prefix}/openapi.json").status_code == 200


def test_a_browser_may_call_it_from_anywhere(client):
    """As /v1 has always allowed - half its callers are web pages."""
    response = client.get("/v1/health", headers={"Origin": "https://example.org"})

    assert response.headers["access-control-allow-origin"] == "*"


def test_the_bytes_are_the_ones_php_would_have_written(client, search_ch):
    """Not just the same data - the same encoding.

    `json_encode` escapes non-ASCII and forward slashes; nothing else does.
    Both decode to the same string, so a client that parses JSON cannot tell -
    but one that matches on raw bytes can, and there are tens of thousands of
    unattended callers nobody can survey.
    """
    search_ch.returns([{"label": "Zürich HB", "id": "8503000", "dist": 1}])

    raw = client.get("/v1/locations", params={"query": "Z"}).content

    assert b"Z\\u00fcrich HB" in raw
    assert "ü".encode() not in raw


def test_a_slash_in_a_value_is_escaped_too(client, search_ch):
    search_ch.returns(
        {
            "stop": {"id": "1", "name": "Somewhere"},
            "connections": [{"time": "2026-09-24 09:00:00", "track": "43/44"}],
        }
    )

    raw = client.get("/v1/stationboard", params={"station": "x"}).content

    assert b'"43\\/44"' in raw
