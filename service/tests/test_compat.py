"""What /v1 does around its answers: HEAD, headers, unknown routes, error bytes.

Each expectation is what the PHP host answered on 24. September 2026.
"""

from conftest import station

from transport_api.encoding import PhpErrorJson

BERN = station("8507000", "Bern", 46.948832, 7.439131, icon="train")


def test_head_is_answered_like_get_without_a_body(client, timetable):
    timetable.returns([BERN])

    response = client.head("/v1/locations", params={"query": "Bern"})

    assert response.status_code == 200
    assert response.content == b""
    assert response.headers["content-type"] == "application/json"


def test_every_answer_allows_any_origin_and_no_caching(client, timetable):
    timetable.returns([BERN])

    response = client.get("/v1/locations", params={"query": "Bern"})

    assert response.headers["access-control-allow-origin"] == "*"
    assert response.headers["cache-control"] == "no-cache"


def test_the_origin_header_is_not_doubled(client, timetable):
    timetable.returns([BERN])

    response = client.get(
        "/v1/locations", params={"query": "Bern"}, headers={"Origin": "https://example.org"}
    )

    assert response.headers.get_list("access-control-allow-origin") == ["*"]


def test_an_unknown_path_is_symfonys_404(client):
    response = client.get("/v1/nothing")

    assert response.status_code == 404
    assert response.content == (
        b'{"errors":[{"message":"No route found for \\u0022GET \\/v1\\/nothing\\u0022"}]}'
    )


def test_a_trailing_slash_is_another_path_not_a_redirect(client):
    response = client.get("/v1/locations/", follow_redirects=False)

    assert response.status_code == 404
    assert response.json() == {"errors": [{"message": 'No route found for "GET /v1/locations/"'}]}


def test_another_method_is_symfonys_405(client):
    response = client.post("/v1/locations", params={"query": "Bern"})

    assert response.status_code == 405
    assert response.json() == {
        "errors": [
            {"message": 'No route found for "POST /v1/locations": Method Not Allowed (Allow: GET)'}
        ]
    }
    assert response.headers["allow"] == "GET"


def test_an_error_envelope_is_encoded_with_the_hex_flags():
    """What PHP prints for json_encode($value, 15) - checked with php -r."""
    body = PhpErrorJson(
        content={"errors": [{"message": 'a: {"error":"<b>x & y</b> it\'s"} a/b ü \\ end\\'}]}
    ).body

    assert body == (
        b'{"errors":[{"message":"a: {\\u0022error\\u0022:\\u0022\\u003Cb\\u003Ex \\u0026 y'
        b'\\u003C\\/b\\u003E it\\u0027s\\u0022} a\\/b \\u00fc \\\\ end\\\\"}]}'
    )
