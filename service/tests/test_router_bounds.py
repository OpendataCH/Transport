"""What is passed on to the router stays within bounds."""

import asyncio
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from transport_api import errors, settings
from transport_api.timetable import connections, map, ojp, router, routing_ui, stationboard


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(settings, "MOTIS_URL", "http://motis:8080")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(400, stream=httpx.ByteStream(b"{}"))

    app = FastAPI()
    errors.install(app)
    app.include_router(routing_ui.router)
    app.include_router(ojp.router)
    app.state.motis = httpx.AsyncClient(
        base_url="http://motis:8080", transport=httpx.MockTransport(handler)
    )
    with TestClient(app) as client:
        client.seen = seen
        yield client


def sent(api) -> dict[str, list[str]]:
    return parse_qs(api.seen[-1].url.query.decode())


@pytest.mark.parametrize(
    "path",
    [
        "/routing/",
        "/routing/index.html",
        "/routing/_app/immutable/chunks/a-b_c.js",
        "/routing/glyphs/Noto%20Sans%20Bold/0-255.pbf",
        "/routing/sprites/basics/sprites@2x.json",
        "/routing/sprite_sdf@2x.png",
        "/routing/icons/rental/bike_station.svg",
        "/routing/site.webmanifest",
        "/routing/tiles/8/133/90.mvt",
        "/tiles/8/133/90.mvt",
    ],
)
def test_the_pages_files_pass(api, path):
    api.get(path)
    assert len(api.seen) == 1


@pytest.mark.parametrize("prefix", ["/api/", "/routing/api/"])
@pytest.mark.parametrize("endpoint", sorted(routing_ui.ALLOWED_API))
def test_the_pages_endpoints_pass(api, prefix, endpoint):
    query = "?startTime=2026-11-22T10:00:00.000Z&endTime=2026-11-22T10:02:00.000Z"
    api.get(prefix + endpoint + query)
    assert api.seen[-1].url.path == "/api/" + endpoint


@pytest.mark.parametrize(
    "path",
    [
        "/routing/metrics",
        "/routing/gtfsrt",
        "/routing/ojp20",
        "/routing/api/debug/transfers",
        "/routing/api/v1/plan",
        "/routing/api/mcp",
        "/api/v6/planner",
        "/api/v6/plan/more",
        "/api/v1/map/%2e%2e/%2e%2e/debug/transfers",
        "/routing/_app/%2e%2e/metrics",
        "/routing/%2Fmetrics",
        "/routing/icons/%3F/x",
        "/routing/tiles/%2e%2e/metrics",
        "/tiles/%2e%2e/metrics",
        "/tiles/99/1/1.mvt",
    ],
)
def test_nothing_else_passes(api, path):
    assert api.get(path).status_code == 404
    assert api.seen == []


@pytest.mark.parametrize(
    ("name", "value", "asked"),
    [
        ("numItineraries", "-4", None),
        ("numItineraries", "0", None),
        ("numItineraries", "x", None),
        ("numItineraries", "nan", None),
        ("numItineraries", "-inf", None),
        ("numItineraries", "inf", "32"),
        ("numItineraries", "999", "32"),
        ("numItineraries", "5", "5"),
        ("maxItineraries", "999", "32"),
        ("numLegAlternatives", "50", "5"),
        ("searchWindow", "900", "900"),
        ("searchWindow", "999999", "86400"),
        ("maxPreTransitTime", "-1", None),
        ("pedestrianSpeed", "1.4", "1.4"),
        ("n", "-1", None),
        ("n", "9999", "256"),
        ("numResults", "999", "50"),
        ("viaMinimumStay", "0,5", "0,5"),
        ("viaMinimumStay", "0,-5", None),
    ],
)
def test_numbers_are_kept_in_range(api, name, value, asked):
    api.get("/routing/api/v6/plan", params={name: value})
    assert sent(api).get(name) == ([asked] if asked else None)


def test_a_number_is_passed_once_and_odd_names_not_at_all(api):
    api.get("/api/v6/plan?numItineraries=3&numItineraries=7&odd%20name=1&via=a&via=b")
    assert sent(api) == {"numItineraries": ["7"], "via": ["a", "b"], "timeout": ["20"]}


def test_a_plan_has_a_timeout(api):
    api.get("/api/v6/plan", params={"timeout": "90"})
    assert sent(api)["timeout"] == ["20"]


@pytest.mark.parametrize(
    ("start", "end", "status"),
    [
        ("2026-11-22T10:00:00.000Z", "2026-11-22T10:02:00.000Z", 400),  # the stub's answer
        ("2026-11-22T10:00:00Z", "2026-11-23T10:00:00Z", 422),
        ("2026-11-22T10:02:00Z", "2026-11-22T10:00:00Z", 422),
        ("2026-11-22T10:00:00", "2026-11-22T10:02:00Z", 422),
        ("soon", "2026-11-22T10:02:00Z", 422),
    ],
)
def test_vehicles_are_drawn_for_an_hour_at_most(api, start, end, status):
    response = api.get("/api/v6/map/trips", params={"startTime": start, "endTime": end})
    if status == 422:
        assert response.status_code == 400
        assert api.seen == []
    else:
        assert len(api.seen) == 1


@pytest.mark.parametrize("endpoint", ["v6/plan", "v6/one-to-all", "v6/refresh-itinerary"])
@pytest.mark.parametrize("semaphore", ["_plans", "_page_plans"])
def test_a_search_of_the_page_waits_for_a_slot(api, monkeypatch, endpoint, semaphore):
    owner = router if semaphore == "_plans" else routing_ui
    monkeypatch.setattr(owner, semaphore, asyncio.Semaphore(0))
    monkeypatch.setattr(settings, "MOTIS_QUEUE_SECONDS", 0.01)
    assert api.get("/api/" + endpoint).status_code == 429
    assert api.seen == []
    # A file does not wait.
    api.get("/routing/favicon.ico")
    assert len(api.seen) == 1


def request_body(inner: str) -> str:
    return (
        f'<OJP xmlns="{ojp.OJP}" xmlns:siri="{ojp.SIRI}"><OJPRequest><siri:ServiceRequest>'
        f"{inner}</siri:ServiceRequest></OJPRequest></OJP>"
    )


@pytest.mark.parametrize(
    ("kind", "given", "asked"),
    [
        ("OJPTripRequest", "-4", "5"),
        ("OJPTripRequest", "x", "5"),
        ("OJPTripRequest", "", "5"),
        ("OJPTripRequest", "999", "32"),
        ("OJPTripRequest", "4", "4"),
        ("OJPStopEventRequest", "-4", "20"),
        ("OJPStopEventRequest", "²", "20"),
        ("OJPStopEventRequest", "9999", "1024"),
        ("OJPStopEventRequest", "3", "6"),
    ],
)
def test_an_ojp_count_is_kept_in_range(api, kind, given, asked):
    body = request_body(
        f"<{kind}><Params><NumberOfResults>{given}</NumberOfResults></Params></{kind}>"
    )
    api.post("/ojp20", content=body.encode())
    root = ET.fromstring(api.seen[-1].content)
    assert [e.text for e in root.iter(f"{{{ojp.OJP}}}NumberOfResults")] == [asked]


def test_every_ojp_count_is_kept_in_range(api):
    count = "<Params><NumberOfResults>{}</NumberOfResults></Params>"
    body = request_body(f"<OJPTripRequest>{count.format(4)}{count.format(999)}</OJPTripRequest>")
    api.post("/ojp20", content=body.encode())
    root = ET.fromstring(api.seen[-1].content)
    assert [e.text for e in root.iter(f"{{{ojp.OJP}}}NumberOfResults")] == ["4", "32"]


@pytest.mark.parametrize(
    "inner",
    [
        "<OJPTripRequest/><OJPLocationInformationRequest/>",
        "<OJPTripRequest/><OJPTripRequest/>",
    ],
)
def test_one_request_at_a_time(api, inner):
    assert api.post("/ojp20", content=request_body(inner).encode()).status_code == 400
    assert api.seen == []


def test_numbers_beyond_counting():
    assert connections._number("-inf", 4) < 1
    assert connections._number("inf", 4) > connections.MAX_LIMIT
    assert connections._number("1e400", 0) > connections.MAX_PAGE
    assert connections._number("nan", 4) == 4
    assert stationboard._count("-inf") == 1


def test_the_map_waits_for_a_slot(monkeypatch):
    monkeypatch.setattr(router, "_plans", asyncio.Semaphore(0))
    monkeypatch.setattr(settings, "MOTIS_QUEUE_SECONDS", 0.01)

    class Never:
        async def get(self, path, params):
            raise AssertionError("asked without a slot")

    with pytest.raises(errors.ApiError) as refused:
        asyncio.run(map._one_to_all(Never(), {"one": "47,8"}))
    assert refused.value.status_code == 429
