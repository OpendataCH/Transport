"""What this service must *not* answer.

nginx sends only /v2/ here. These tests make the other half of that agreement
explicit: if a location block is ever written too broadly, the service refuses
the request instead of shadowing the PHP application with a half-built answer.
"""

import pytest


@pytest.mark.parametrize(
    "path",
    [
        "/",
        "/v1/",
        "/v1/locations",
        "/v1/connections",
        "/v1/stationboard",
        "/swagger.json",
        "/stats",
    ],
)
def test_v1_surface_is_not_served_here(client, path):
    assert client.get(path).status_code == 404


def test_openapi_lives_under_the_prefix(client):
    assert client.get("/openapi.json").status_code == 404

    document = client.get("/v2/openapi.json")
    assert document.status_code == 200
    # FastAPI emits OpenAPI 3.1; /v1 serves a generated Swagger 2.0 document
    # from the PHP application. Two documents, two addresses, on purpose.
    assert document.json()["openapi"].startswith("3.1")
    assert set(document.json()["paths"]) == {"/v2/health"}
