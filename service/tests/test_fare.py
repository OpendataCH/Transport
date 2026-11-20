"""`POST /v1/fare`: a /v1 connection priced by NOVA, kept per route, within the quota."""

from datetime import date
from types import SimpleNamespace

import fakeredis
import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from transport_api import settings
from transport_api.timetable import fare


def section(start, end, departure, arrival, category="IC", operator="SBB"):
    return {
        "journey": {"category": category, "operator": operator, "name": "000707"},
        "walk": None,
        "departure": {"station": {"id": start}, "departure": departure},
        "arrival": {"station": {"id": end}, "arrival": arrival},
    }


WALK = {
    "journey": None,
    "walk": {"duration": 240},
    "departure": {"station": {"id": "8576646"}, "departure": "2026-11-20T07:27:00+0100"},
    "arrival": {"station": {"id": "8507000"}, "arrival": "2026-11-20T07:31:00+0100"},
}

BERN_ZURICH = {
    "sections": [
        WALK,
        section("8507000", "8503000", "2026-11-20T07:31:00+0100", "2026-11-20T08:28:00+0100"),
    ]
}


def answer(*products: tuple[int, int, str, str]) -> bytes:
    """A NOVA answer: (first leg, last leg, class, price) per product."""
    results = "".join(
        f"<ns2:TripFareResult><ns2:FromLegIdRef>{f}</ns2:FromLegIdRef>"
        f"<ns2:ToLegIdRef>{t}</ns2:ToLegIdRef><ns2:FareProduct>"
        f"<ns2:FareProductName>Streckenbillett</ns2:FareProductName>"
        f"<ns2:Price>{p}</ns2:Price><ns2:FareClass>{c}</ns2:FareClass>"
        f"</ns2:FareProduct></ns2:TripFareResult>"
        for f, t, c, p in products
    )
    return (
        '<ns2:OJP xmlns:ns2="http://www.vdv.de/ojp"><ns2:OJPResponse>'
        f"<ns2:FareResult>{results}</ns2:FareResult></ns2:OJPResponse></ns2:OJP>"
    ).encode()


def test_the_rides_are_taken_with_the_operators_number_and_utc():
    assert fare.rides(BERN_ZURICH) == [
        {
            "from": "8507000",
            "to": "8503000",
            "departure": "2026-11-20T06:31:00Z",
            "arrival": "2026-11-20T07:28:00Z",
            "category": "IC",
            "operator": "11",
            "via": [],
        }
    ]
    with pytest.raises(fare.Unpriceable):
        fare.rides({"sections": [WALK]})
    with pytest.raises(fare.Unpriceable):
        fare.rides({"sections": [section("1", "2", "x", "y", operator="Nobody Ltd")]})


def test_a_route_is_the_same_at_any_time_of_the_year_but_not_across_the_change():
    later = section("8507000", "8503000", "2026-11-27T18:01:00+0100", "2026-11-27T18:58:00+0100")
    assert fare.cache_key(fare.rides(BERN_ZURICH)) == fare.cache_key(
        fare.rides({"sections": [later]})
    )
    after = section("8507000", "8503000", "2026-12-14T07:31:00+0100", "2026-12-14T08:28:00+0100")
    assert fare.cache_key(fare.rides(BERN_ZURICH)) != fare.cache_key(
        fare.rides({"sections": [after]})
    )
    # The timetable changes on the second Sunday of December.
    assert fare.timetable_year(date(2026, 12, 12)) == 2026
    assert fare.timetable_year(date(2026, 12, 13)) == 2027


def test_prices_cover_the_whole_trip_or_add_up_stretch_by_stretch():
    whole = answer((1, 1, "firstClass", "45.50"), (1, 1, "secondClass ", "26.50"))
    assert fare.prices(whole, 1) == {"1st": 45.5, "2nd": 26.5}
    stretches = answer((1, 1, "secondClass", "10.00"), (2, 2, "secondClass", "4.40"))
    assert fare.prices(stretches, 2) == {"2nd": 14.4}
    gap = answer((1, 1, "secondClass", "10.00"))
    assert fare.prices(gap, 2) == {}


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(settings, "OJP_FARE_KEY", "key")
    calls: list[bytes] = []

    def nova(request: httpx.Request) -> httpx.Response:
        calls.append(request.content)
        if b"HTA" in request.content:
            return httpx.Response(200, content=answer((1, 1, "secondClass ", "26.50")))
        return httpx.Response(200, content=answer((1, 1, "secondClass ", "53.00")))

    transport = httpx.MockTransport(nova)
    real = httpx.AsyncClient
    monkeypatch.setattr(fare.httpx, "AsyncClient", lambda: real(transport=transport))
    app = FastAPI()
    app.include_router(fare.router, prefix="/v1")
    redis = fakeredis.FakeAsyncRedis(decode_responses=True)
    app.state.statistics = SimpleNamespace(redis=redis)
    with TestClient(app) as client:
        client.calls = calls
        client.redis = redis
        yield client


def test_a_connection_is_priced_once_and_then_kept(api):
    first = api.post("/v1/fare", json=BERN_ZURICH)
    assert first.status_code == 200
    assert first.json() == {
        "currency": "CHF",
        "product": "Streckenbillett",
        "fares": {"2nd": {"full": 53.0, "halfFare": 26.5}},
    }
    assert len(api.calls) == 2
    assert b"<siri:OperatorRef>11</siri:OperatorRef>" in api.calls[0]
    assert b'<ShortName><Text xml:lang="de">IC</Text></ShortName>' in api.calls[0]

    later = section("8507000", "8503000", "2026-11-20T09:31:00+0100", "2026-11-20T10:28:00+0100")
    again = api.post("/v1/fare", json={"sections": [later]})
    assert again.json() == first.json()
    assert len(api.calls) == 2


def test_the_quota_is_kept(api, monkeypatch):
    monkeypatch.setattr(settings, "FARE_PER_MINUTE", 3)
    assert api.post("/v1/fare", json=BERN_ZURICH).status_code == 200
    other = section("8507000", "8500218", "2026-11-20T07:31:00+0100", "2026-11-20T07:58:00+0100")
    busy = api.post("/v1/fare", json={"sections": [other]})
    assert busy.status_code == 503
    assert len(api.calls) == 2


def test_what_cannot_be_priced_is_refused(api, monkeypatch):
    assert api.post("/v1/fare", json={"sections": [WALK]}).status_code == 400
    assert api.post("/v1/fare", json={"sections": "x"}).status_code == 400
    monkeypatch.setattr(settings, "OJP_FARE_KEY", None)
    assert api.post("/v1/fare", json=BERN_ZURICH).status_code == 503


def test_the_stops_between_are_sent_and_tell_routes_apart():
    """Bern-Spiez runs via Thun or via Belp: NOVA prices it only with the stops."""

    def ride(via):
        leg = section("8507000", "8507483", "2026-11-20T20:34:00+0100", "2026-11-20T21:03:00+0100")
        leg["journey"]["passList"] = [
            {"station": {"id": "8507000"}, "arrival": None, "departure": "2026-11-20T20:34:00+0100"},
            {"station": {"id": via}, "arrival": "2026-11-20T20:51:00+0100", "departure": "2026-11-20T20:53:00+0100"},
            {"station": {"id": "8507483"}, "arrival": "2026-11-20T21:03:00+0100", "departure": None},
        ]
        return {"sections": [leg]}

    thun = fare.rides(ride("8507100"))
    assert thun[0]["via"] == [
        {"id": "8507100", "arrival": "2026-11-20T19:51:00Z", "departure": "2026-11-20T19:53:00Z"}
    ]
    body = fare.request_body(thun, fare.NO_CARD).decode()
    assert "<LegIntermediate><siri:StopPointRef>8507100</siri:StopPointRef>" in body
    assert "<Order>2</Order></LegIntermediate><LegAlight>" in body
    assert "<Order>3</Order></LegAlight>" in body
    assert fare.cache_key(thun) != fare.cache_key(fare.rides(ride("8507050")))
