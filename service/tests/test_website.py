"""The website around the API, served as Apache served the PHP application's web/."""

import pytest

from transport_api import statistics
from transport_api.main import app


@pytest.mark.parametrize(
    ("path", "media_type"),
    [
        ("/", "text/html"),
        ("/index.html", "text/html"),
        ("/docs.html", "text/html"),
        ("/showcase.html", "text/html"),
        ("/examples/", "text/html"),
        ("/examples/connections.html", "text/html"),
        ("/swagger.json", "application/json"),
        ("/robots.txt", "text/plain"),
        ("/favicon.ico", "image/vnd.microsoft.icon"),
        ("/media/css/layout.css", "text/css"),
    ],
)
def test_the_pages_and_files_are_served(client, path, media_type):
    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith(media_type)


def test_the_landing_page_is_the_index(client):
    assert client.get("/").content == client.get("/index.html").content


def test_the_swagger_document_is_the_one_php_generated(client):
    """Swagger 2.0, frozen - clients that read /swagger.json keep reading the same."""
    document = client.get("/swagger.json").json()

    assert document["swagger"] == "2.0"
    assert {"/locations", "/connections", "/stationboard"} <= set(document["paths"])


def test_a_directory_without_its_slash_is_redirected(client):
    response = client.get("/examples", follow_redirects=False)

    assert response.status_code == 301
    assert response.headers["location"] == "/examples/"


def test_the_php_example_moved_with_its_query(client):
    response = client.get(
        "/examples/connections.php", params={"from": "Bern", "to": "Zug"}, follow_redirects=False
    )

    assert response.status_code == 301
    assert response.headers["location"] == "/examples/connections.html?from=Bern&to=Zug"


def test_head_is_answered_like_get_without_a_body(client):
    response = client.head("/docs.html")

    assert response.status_code == 200
    assert response.content == b""


@pytest.mark.parametrize("path", ["/nothing", "/media/", "/../pyproject.toml", "/%2e%2e/main.py"])
def test_what_is_not_a_file_is_the_apis_404(client, path):
    response = client.get(path)

    assert response.status_code == 404
    assert response.json()["errors"][0]["message"].startswith("No route found for")


def test_a_post_to_an_unknown_path_stays_a_404(client):
    """Not a 405: the website is looked up after routing, not by a catch-all route."""
    assert client.post("/nothing").status_code == 404


def test_the_website_is_not_counted(client):
    class Recorder:
        def __init__(self):
            self.paths = []

        async def record(self, *, path, **_):
            self.paths.append(path)

    recorder = Recorder()
    app.state.statistics = recorder
    try:
        client.get("/docs.html")
        client.get("/examples")
        client.get("/nothing")
    finally:
        app.state.statistics = None

    # An unknown path is still a counted 404, as it was in the PHP.
    assert recorder.paths == ["/nothing"]
    assert statistics.exception_for(404, None) == statistics.NOT_FOUND
