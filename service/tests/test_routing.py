"""What this service answers, and what it leaves alone.

`/v1` is this service's own prefix and `/v2` its alias; both answer from our
own timetable (timetable/). The website around the API is served here too;
see test_website.py.
"""

import pytest
from conftest import station

PREFIXES = ["/v1", "/v2"]


@pytest.mark.parametrize("prefix", PREFIXES)
def test_both_prefixes_answer(client, prefix):
    assert client.get(f"{prefix}/health").json()["status"] == "ok"


@pytest.mark.parametrize("prefix", PREFIXES)
def test_without_a_database_both_prefixes_say_so(client, prefix):
    """There is no other source to fall back to."""
    answer = client.get(f"{prefix}/locations", params={"query": "Bern"})
    assert answer.status_code == 503
    assert "not configured" in answer.json()["errors"][0]["message"]


def test_the_api_version_is_the_one_the_prefix_promises(client):
    """`/v1/` has always said 1.0, and its answer is compared byte for byte."""
    assert client.get("/v1/").json()["version"] == "1.0"
    assert client.get("/v2/").json()["version"] == "2.0"


def test_the_documents_live_under_the_documented_prefix(client):
    assert client.get("/openapi.json").status_code == 404

    document = client.get("/v1/openapi.json")
    assert document.status_code == 200
    # FastAPI emits OpenAPI 3.1; the Swagger 2.0 document the PHP application
    # generated stays at /swagger.json. Two documents, two addresses, on purpose.
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


def test_the_bytes_are_the_ones_php_would_have_written(client, timetable):
    """Not just the same data - the same encoding.

    `json_encode` escapes non-ASCII and forward slashes; nothing else does.
    Both decode to the same string, so a client that parses JSON cannot tell -
    but one that matches on raw bytes can, and there are tens of thousands of
    unattended callers nobody can survey.
    """
    timetable.returns([station("8503000", "Zürich HB", 47.378177, 8.540212)])

    raw = client.get("/v1/locations", params={"query": "Z"}).content

    assert b"Z\\u00fcrich HB" in raw
    assert "ü".encode() not in raw


def test_a_slash_in_a_value_is_escaped_too(client, timetable):
    timetable.returns([station(None, "Bern, Bahnhof/Bubenbergplatz", 46.948, 7.439)])

    raw = client.get("/v1/locations", params={"query": "x"}).content

    assert b'"Bern, Bahnhof\\/Bubenbergplatz"' in raw


def test_plans_beyond_the_router_capacity_are_refused(monkeypatch):
    import asyncio

    from transport_api import errors, settings
    from transport_api.timetable import router

    monkeypatch.setattr(settings, "MOTIS_CONCURRENCY", 1)
    monkeypatch.setattr(settings, "MOTIS_QUEUE_SECONDS", 0.05)
    monkeypatch.setattr(router, "_plans", None)

    class Slow(router.Motis):
        async def get(self, path, params):
            await asyncio.sleep(0.2)
            return {"itineraries": []}

    async def two():
        motis = Slow(None)
        return await asyncio.gather(motis.plan({}), motis.plan({}), return_exceptions=True)

    first, second = asyncio.run(two())
    assert first == {"itineraries": []}
    assert isinstance(second, errors.ApiError) and second.status_code == 429
    monkeypatch.setattr(router, "_plans", None)
