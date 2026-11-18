"""`/ojp20` passed through to the router, with Swiss stop ids and valid OJP 2.0."""

import asyncio
import xml.etree.ElementTree as ET

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from transport_api import settings
from transport_api.timetable import ojp, router

J = "{http://www.vdv.de/ojp}"
S = "{http://www.siri.org.uk/siri}"

# A trip request as the national planner's clients write it: SIRI as the
# default namespace and `ojp:` for OJP, which the router cannot read.
TRIP_REQUEST = b"""<?xml version="1.0" encoding="utf-8"?>
<ojp:OJP xmlns="http://www.siri.org.uk/siri" xmlns:ojp="http://www.vdv.de/ojp" version="2.0">
  <ojp:OJPRequest>
    <ServiceRequest>
      <ServiceRequestContext><Language>de</Language></ServiceRequestContext>
      <RequestTimestamp>2026-11-19T07:00:00Z</RequestTimestamp>
      <RequestorRef>test</RequestorRef>
      <ojp:OJPTripRequest>
        <RequestTimestamp>2026-11-19T07:00:00Z</RequestTimestamp>
        <ojp:Origin>
          <ojp:PlaceRef>
            <ojp:StopPlaceRef>8507000</ojp:StopPlaceRef>
            <ojp:Name><ojp:Text>Bern</ojp:Text></ojp:Name>
          </ojp:PlaceRef>
          <ojp:DepArrTime>2026-11-19T07:00:00Z</ojp:DepArrTime>
        </ojp:Origin>
        <ojp:Destination>
          <ojp:PlaceRef>
            <ojp:StopPlaceRef>ch:1:sloid:7100</ojp:StopPlaceRef>
            <ojp:Name><ojp:Text>Thun</ojp:Text></ojp:Name>
          </ojp:PlaceRef>
        </ojp:Destination>
      </ojp:OJPTripRequest>
    </ServiceRequest>
  </ojp:OJPRequest>
</ojp:OJP>"""

STOP_EVENT_REQUEST = b"""<OJP xmlns="http://www.vdv.de/ojp"
 xmlns:siri="http://www.siri.org.uk/siri" version="2.0">
<OJPRequest><siri:ServiceRequest>
<OJPStopEventRequest><Location><PlaceRef>
<StopPlaceRef>ch:1:sloid:7100</StopPlaceRef></PlaceRef></Location></OJPStopEventRequest>
</siri:ServiceRequest></OJPRequest></OJP>"""

# What MOTIS 2.11.4 answers, cut down to what it gets wrong: a station ref in
# the SIRI namespace, the line in the OJP one, a departure before the arrival,
# texts without <Text>, the public code twice, the length of the line in points.
ROUTER_ANSWER = b"""<?xml version="1.0" encoding="utf-8"?>
<OJP xmlns:siri="http://www.siri.org.uk/siri" xmlns="http://www.vdv.de/ojp" version="2.0">
  <OJPResponse><siri:ServiceDelivery>
    <siri:ResponseTimestamp>2026-11-18T20:25:36Z</siri:ResponseTimestamp>
    <siri:ProducerRef>MOTIS</siri:ProducerRef>
    <OJPTripDelivery>
      <siri:ResponseTimestamp>2026-11-18T20:25:36Z</siri:ResponseTimestamp>
      <siri:DefaultLanguage>de</siri:DefaultLanguage>
      <TripResponseContext><Places>
        <Place><StopPlace>
          <siri:StopPlaceRef>ch_Parentch:1:sloid:7000</siri:StopPlaceRef>
          <StopPlaceName><Text xml:lang="de">Bern</Text></StopPlaceName>
        </StopPlace><Name><Text xml:lang="de">Bern</Text></Name>
        <GeoPosition><siri:Longitude>7.43913</siri:Longitude><siri:Latitude>46.94883</siri:Latitude></GeoPosition></Place>
      </Places></TripResponseContext>
      <TripResult><Id>1</Id><Trip>
        <Id>1</Id><Duration>PT30M</Duration>
        <StartTime>2026-11-19T07:16:00Z</StartTime><EndTime>2026-11-19T07:46:00Z</EndTime>
        <Transfers>0</Transfers><Distance>10</Distance>
        <Leg><Id>1</Id><Duration>PT30M</Duration><TimedLeg>
          <LegBoard>
            <siri:StopPointRef>ch_ch:1:sloid:7000:5:10</siri:StopPointRef>
            <StopPointName>Bern</StopPointName>
            <PlannedQuay>10</PlannedQuay>
            <ServiceDeparture><TimetabledTime>2026-11-19T07:16:00Z</TimetabledTime></ServiceDeparture>
            <Order>1</Order>
          </LegBoard>
          <LegIntermediate>
            <siri:StopPointRef>ch_ch:1:sloid:16161:1:2</siri:StopPointRef>
            <StopPointName><Text xml:lang="de">Bern Wankdorf</Text></StopPointName>
            <ServiceDeparture><TimetabledTime>2026-11-19T07:19:00Z</TimetabledTime></ServiceDeparture>
            <ServiceArrival><TimetabledTime>2026-11-19T07:19:00Z</TimetabledTime></ServiceArrival>
            <Order>2</Order>
          </LegIntermediate>
          <LegAlight>
            <siri:StopPointRef>ch_8301700</siri:StopPointRef>
            <StopPointName><Text xml:lang="de">Milano Centrale</Text></StopPointName>
            <ServiceArrival><TimetabledTime>2026-11-19T07:46:00Z</TimetabledTime></ServiceArrival>
            <Order>3</Order>
          </LegAlight>
          <Service>
            <OperatingDayRef>20261119</OperatingDayRef>
            <JourneyRef>20261119_07:42_ch_.ojp-91-1-E.1.TA.581.j26</JourneyRef>
            <PublicCode>RE1</PublicCode>
            <PublicCode>RE1</PublicCode>
            <LineRef>ch_91-1-E-j26-1</LineRef>
            <DirectionRef>0</DirectionRef>
            <siri:OperatorRef>33</siri:OperatorRef>
            <ProductCategory />
            <DestinationText><Text xml:lang="de">Thun</Text></DestinationText>
            <PublishedServiceName><Text xml:lang="de">RE1</Text></PublishedServiceName>
            <Mode><PtMode>rail</PtMode></Mode>
          </Service>
        </TimedLeg></Leg>
      </Trip></TripResult>
    </OJPTripDelivery>
  </siri:ServiceDelivery></OJPResponse>
</OJP>"""


@pytest.fixture
def api(monkeypatch):
    monkeypatch.setattr(settings, "MOTIS_URL", "http://motis:8080")
    seen: list[bytes] = []
    answers: list[httpx.Response] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ojp20"
        seen.append(request.content)
        return answers.pop(0) if answers else httpx.Response(200, content=ROUTER_ANSWER)

    app = FastAPI()
    app.include_router(ojp.router)
    app.state.motis = httpx.AsyncClient(
        base_url="http://motis:8080", transport=httpx.MockTransport(handler)
    )
    with TestClient(app) as client:
        client.seen = seen
        client.answers = answers
        yield client


@pytest.mark.parametrize(
    ("given", "router_id"),
    [
        ("8507000", "ch_Parentch:1:sloid:7000"),
        ("8500258", "ch_Parentch:1:sloid:258"),
        ("ch:1:sloid:7000", "ch_Parentch:1:sloid:7000"),
        ("ch:1:sloid:7000:4:8", "ch_ch:1:sloid:7000:4:8"),
        ("8301700", "ch_Parent8301700"),
        ("8002301_gen:missingSLOID_pf:21", "ch_8002301_gen:missingSLOID_pf:21"),
        ("ch_Parentch:1:sloid:7000", "ch_Parentch:1:sloid:7000"),
        (" 8507000 ", "ch_Parentch:1:sloid:7000"),
    ],
)
def test_a_client_stop_id_becomes_the_routers(given, router_id):
    assert ojp.to_router(given) == router_id


@pytest.mark.parametrize(
    ("router_id", "public"),
    [
        ("ch_Parentch:1:sloid:7000", "8507000"),
        ("ch_Parentch:1:sloid:76646", "8576646"),
        ("ch_ch:1:sloid:7000:4:8", "ch:1:sloid:7000:4:8"),
        ("ch_Parent8301700", "8301700"),
        ("ch_ch:1:sloid:258", "8500258"),
    ],
)
def test_the_routers_stop_id_becomes_the_clients(router_id, public):
    assert ojp.from_router(router_id) == public
    assert ojp.to_router(public) in (router_id, "ch_Parentch:1:sloid:258")


def test_the_request_reaches_the_router_in_its_prefixes_and_ids(api):
    response = api.post("/ojp20", content=TRIP_REQUEST)
    assert response.status_code == 200
    sent = api.seen[0].decode()
    assert '<OJP xmlns="http://www.vdv.de/ojp" xmlns:siri="http://www.siri.org.uk/siri"' in sent
    assert "<OJPRequest><siri:ServiceRequest>" in sent.replace("\n", "").replace(" ", "")
    assert "<StopPlaceRef>ch_Parentch:1:sloid:7000</StopPlaceRef>" in sent
    assert "<StopPlaceRef>ch_Parentch:1:sloid:7100</StopPlaceRef>" in sent
    assert 'version="2.0"' in sent


def test_the_answer_is_repaired(api):
    response = api.post("/ojp20", content=TRIP_REQUEST)
    assert response.headers["content-type"].startswith("text/xml")
    root = ET.fromstring(response.content)

    # Stop ids as clients know them, in the namespace OJP puts them in.
    assert root.find(f".//{S}StopPlaceRef") is None
    assert root.find(f".//{J}StopPlace/{J}StopPlaceRef").text == "8507000"
    assert root.find(f".//{J}OperatingDayRef").text == "2026-11-19"
    refs = [e.text for e in root.iter(f"{S}StopPointRef")]
    assert refs == ["ch:1:sloid:7000:5:10", "ch:1:sloid:16161:1:2", "8301700"]

    # The line in SIRI, in the order of the schema; the public code once.
    service = root.find(f".//{J}Service")
    names = [child.tag for child in service]
    assert names[:5] == [
        f"{J}OperatingDayRef",
        f"{J}JourneyRef",
        f"{J}PublicCode",
        f"{S}LineRef",
        f"{S}DirectionRef",
    ]
    assert names.index(f"{J}PublishedServiceName") < names.index(f"{S}OperatorRef")
    assert names.index(f"{S}OperatorRef") < names.index(f"{J}DestinationText")
    assert f"{J}ProductCategory" not in names
    # The journey is the router's to recognise in a trip info request.
    assert service.find(f"{J}JourneyRef").text.startswith("20261119_07:42_ch_")

    # Arrival before departure; texts in <Text>; no length counted in points.
    intermediate = [child.tag for child in root.find(f".//{J}LegIntermediate")]
    assert intermediate.index(f"{J}ServiceArrival") < intermediate.index(f"{J}ServiceDeparture")
    board = root.find(f".//{J}LegBoard")
    assert board.find(f"{J}StopPointName/{J}Text").text == "Bern"
    assert board.find(f"{J}PlannedQuay/{J}Text").text == "10"
    assert (
        board.find(f"{J}PlannedQuay/{J}Text").get("{http://www.w3.org/XML/1998/namespace}lang")
        == "de"
    )
    assert root.find(f".//{J}Trip/{J}Distance") is None


def test_the_trip_info_placeholder_and_track_are_mended():
    answer = ET.fromstring(
        b"""<OJP xmlns="http://www.vdv.de/ojp" xmlns:siri="http://www.siri.org.uk/siri">
        <PreviousCall><siri:StopPointRef>ch_ch:1:sloid:7000:1:1</siri:StopPointRef>
          <StopPointName><Text>Bern</Text></StopPointName><PlannedQuay>1</PlannedQuay>
          <NameSuffix>PLATFORM_ACCESS_WITHOUT_ASSISTANCE</NameSuffix>
          <ServiceArrival/><ServiceDeparture><TimetabledTime>x</TimetabledTime></ServiceDeparture>
        </PreviousCall>
        <LegTrack><TrackSection>
          <TrackSectionStart><siri:StopPointRef>ch_a</siri:StopPointRef><Name>A</Name>
            <siri:StopPointRef>ch_b</siri:StopPointRef></TrackSectionStart>
          <TrackSectionEnd><Name>B</Name></TrackSectionEnd>
          <Duration>PT10M</Duration><Length>2</Length>
        </TrackSection></LegTrack>
        </OJP>"""
    )
    ojp.repair(answer)
    call = answer.find(f"{J}PreviousCall")
    assert call.find(f"{J}NameSuffix") is None
    assert call.find(f"{J}ServiceArrival") is None
    assert [c.tag for c in call][:3] == [f"{S}StopPointRef", f"{J}StopPointName", f"{J}PlannedQuay"]
    section = answer.find(f".//{J}TrackSection")
    assert [e.text for e in section.find(f"{J}TrackSectionStart").iter(f"{S}StopPointRef")] == ["a"]
    end = section.find(f"{J}TrackSectionEnd")
    assert [c.tag for c in end] == [f"{S}StopPointRef", f"{J}Name"]
    assert end.find(f"{S}StopPointRef").text == "b"
    assert section.find(f"{J}Length") is None


def test_a_stop_event_passes_too(api):
    assert api.post("/ojp20", content=STOP_EVENT_REQUEST).status_code == 200
    assert b"<StopPlaceRef>ch_Parentch:1:sloid:7100</StopPlaceRef>" in api.seen[0]


@pytest.mark.parametrize(
    ("body", "complaint"),
    [
        (b"<OJP", "well-formed"),
        (b'<!DOCTYPE x [<!ENTITY a "b">]><OJP xmlns="http://www.vdv.de/ojp"/>', "document type"),
        (b"<OJP/>", "root element"),
        (b'<OJP xmlns="http://www.vdv.de/ojp"><OJPRequest/></OJP>', "ServiceRequest"),
        (
            b'<OJP xmlns="http://www.vdv.de/ojp" xmlns:siri="http://www.siri.org.uk/siri">'
            b"<OJPRequest><siri:ServiceRequest><OJPFareRequest/></siri:ServiceRequest>"
            b"</OJPRequest></OJP>",
            "Supported are",
        ),
        (b"<x>" + b" " * ojp.MAX_REQUEST_BYTES + b"</x>", "too large"),
        (b"<a>" * 100 + b"</a>" * 100, "too deeply"),
    ],
)
def test_what_is_no_request_is_refused_here(api, body, complaint):
    response = api.post("/ojp20", content=body)
    assert response.status_code == 400
    assert complaint in response.text
    assert api.seen == []


def test_the_routers_refusal_is_passed_on(api):
    api.answers.append(httpx.Response(404, text='{"error":"Could not find timetable location"}'))
    response = api.post("/ojp20", content=TRIP_REQUEST)
    assert response.status_code == 400
    assert "Could not find timetable location" in response.text

    api.answers.append(httpx.Response(500, text='{"error":"geocoding not loaded"}'))
    assert api.post("/ojp20", content=TRIP_REQUEST).status_code == 502


def test_without_a_router_it_says_so(api, monkeypatch):
    monkeypatch.setattr(settings, "MOTIS_URL", None)
    assert api.post("/ojp20", content=TRIP_REQUEST).status_code == 503


def test_a_trip_waits_for_a_plan_slot(api, monkeypatch):
    monkeypatch.setattr(router, "_plans", asyncio.Semaphore(0))
    monkeypatch.setattr(settings, "MOTIS_QUEUE_SECONDS", 0.01)
    assert api.post("/ojp20", content=TRIP_REQUEST).status_code == 429
    # A departure board is cheap and does not wait.
    assert api.post("/ojp20", content=STOP_EVENT_REQUEST).status_code == 200


LOCATION_BY_ID = b"""<OJP xmlns="http://www.vdv.de/ojp" xmlns:siri="http://www.siri.org.uk/siri">
<OJPRequest><siri:ServiceRequest><OJPLocationInformationRequest>
<PlaceRef><StopPlaceRef>8507000</StopPlaceRef></PlaceRef>
</OJPLocationInformationRequest></siri:ServiceRequest></OJPRequest></OJP>"""

LOCATION_BY_AREA = b"""<OJP xmlns="http://www.vdv.de/ojp" xmlns:siri="http://www.siri.org.uk/siri">
<OJPRequest><siri:ServiceRequest><OJPLocationInformationRequest>
<InitialInput><GeoRestriction><Rectangle>
<UpperLeft><siri:Longitude>7.437</siri:Longitude><siri:Latitude>46.95</siri:Latitude></UpperLeft>
<LowerRight><siri:Longitude>7.441</siri:Longitude><siri:Latitude>46.948</siri:Latitude></LowerRight>
</Rectangle></GeoRestriction></InitialInput>
</OJPLocationInformationRequest></siri:ServiceRequest></OJPRequest></OJP>"""


def test_a_stop_lookup_needs_the_routers_place_search(api, monkeypatch):
    monkeypatch.setattr(settings, "MOTIS_GEOCODING", False)
    response = api.post("/ojp20", content=LOCATION_BY_ID)
    assert response.status_code == 400
    assert "by area" in response.text
    assert api.post("/ojp20", content=LOCATION_BY_AREA).status_code == 200
    assert len(api.seen) == 1

    monkeypatch.setattr(settings, "MOTIS_GEOCODING", True)
    assert api.post("/ojp20", content=LOCATION_BY_ID).status_code == 200
    assert b"<StopPlaceRef>ch_Parentch:1:sloid:7000</StopPlaceRef>" in api.seen[-1]


def test_a_transfers_track_goes_into_a_path_guidance_section():
    answer = ET.fromstring(
        b"""<OJP xmlns="http://www.vdv.de/ojp"><TransferLeg><PathGuidance>
        <TrackSection><Duration>PT4M</Duration><Length>7</Length></TrackSection>
        </PathGuidance></TransferLeg>
        <JourneyTrack><TrackSection><Length>1200</Length></TrackSection></JourneyTrack></OJP>"""
    )
    ojp.repair(answer)
    section = answer.find(f".//{J}PathGuidance/{J}PathGuidanceSection/{J}TrackSection")
    assert section is not None
    assert section.find(f"{J}Length") is None
    assert answer.find(f".//{J}JourneyTrack/{J}TrackSection/{J}Length").text == "1200"


def test_a_trip_info_names_the_day_as_the_router_does(api):
    request = b"""<OJP xmlns="http://www.vdv.de/ojp" xmlns:siri="http://www.siri.org.uk/siri">
<OJPRequest><siri:ServiceRequest><OJPTripInfoRequest>
<JourneyRef>20261119_07:42_ch_.ojp-91-1-E.1.TA.581.j26</JourneyRef>
<OperatingDayRef>2026-11-19</OperatingDayRef>
</OJPTripInfoRequest></siri:ServiceRequest></OJPRequest></OJP>"""
    assert api.post("/ojp20", content=request).status_code == 200
    assert b"<OperatingDayRef>20261119</OperatingDayRef>" in api.seen[0]
