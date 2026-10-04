"""`/routing/`, `/api/` and `/tiles/` passed through to the router."""

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from transport_api import settings
from transport_api.timetable import routing_ui


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(settings, "MOTIS_URL", "http://motis:8080")
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.url.path)
        return httpx.Response(200, text="ok", headers={"content-type": "text/plain"})

    app = FastAPI()
    app.include_router(routing_ui.router)
    app.state.motis = httpx.AsyncClient(
        base_url="http://motis:8080", transport=httpx.MockTransport(handler)
    )
    with TestClient(app) as client:
        client.seen = seen
        yield client


def test_the_page_and_its_files_come_from_the_router(api):
    assert api.get("/routing/").text == "ok"
    api.get("/routing/_app/immutable/x.js")
    assert api.seen == ["/", "/_app/immutable/x.js"]


def test_the_page_needs_its_slash(api):
    response = api.get("/routing", follow_redirects=False)
    assert response.status_code == 301
    assert response.headers["location"] == "/routing/"


def test_only_the_endpoints_the_page_uses_pass(api):
    assert api.get("/api/v6/plan", params={"fromPlace": "a"}).status_code == 200
    assert api.get("/api/debug/transfers").status_code == 404
    assert api.seen == ["/api/v6/plan"]


def test_without_a_router_it_says_so(api, monkeypatch):
    monkeypatch.setattr(settings, "MOTIS_URL", None)
    assert api.get("/routing/").status_code == 503
