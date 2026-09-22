"""`/v1/stationboard`, against the answer the PHP implementation is recorded to give."""

import json
from datetime import datetime

import pytest
from conftest import fixture

from transport_api.models import StationBoardResponse

PARAMS = {"station": "008591052", "limit": "3", "datetime": "2015-12-23T14:20:00"}


def test_the_answer_is_the_one_v1_records(client, search_ch):
    """The recorded pair the PHP suite asserts, asserted here."""
    search_ch.returns(fixture("stationboard/searchch_response_2016-12-23.json"))

    body = client.get("/v1/stationboard", params=PARAMS).json()

    assert body == fixture("stationboard/response_2016-12-23.json")


def test_the_answer_matches_its_own_description(client, search_ch):
    search_ch.returns(fixture("stationboard/searchch_response_2016-12-23.json"))

    body = client.get("/v1/stationboard", params=PARAMS).json()

    StationBoardResponse.model_validate(body)


def test_the_keys_are_in_the_order_v1_writes_them(client, search_ch):
    search_ch.returns(fixture("stationboard/searchch_response_2016-12-23.json"))

    journey = client.get("/v1/stationboard", params=PARAMS).json()["stationboard"][0]

    assert list(journey) == [
        "stop",
        "name",
        "category",
        "subcategory",
        "categoryCode",
        "number",
        "operator",
        "to",
        "passList",
        "capacity1st",
        "capacity2nd",
    ]
    assert list(journey["stop"]) == [
        "station",
        "arrival",
        "arrivalTimestamp",
        "departure",
        "departureTimestamp",
        "delay",
        "platform",
        "prognosis",
        "realtimeAvailability",
        "location",
    ]


def test_the_upstream_is_asked_the_way_v1_asks(client, search_ch):
    search_ch.returns(fixture("stationboard/searchch_response_2016-12-23.json"))

    client.get("/v1/stationboard", params=PARAMS)

    sent = search_ch.last.url.params
    assert sent["stop"] == "008591052"
    assert sent["date"] == "2015-12-23"
    assert sent["time"] == "14:20"
    assert sent["mode"] == "depart"
    assert sent["limit"] == "3"
    # Without these three there are no platforms, no onward stops, no delays.
    assert sent["show_tracks"] == "1"
    assert sent["show_subsequent_stops"] == "1"
    assert sent["show_delays"] == "1"
    assert "transportation_types" not in sent


def test_arrivals_are_a_mode_not_a_filter(client, search_ch):
    client.get("/v1/stationboard", params={"station": "Bern", "type": "arrival"})

    assert search_ch.last.url.params["mode"] == "arrival"


def test_the_id_parameter_stands_in_for_the_station(client, search_ch):
    client.get("/v1/stationboard", params={"id": "8503000"})

    assert search_ch.last.url.params["stop"] == "8503000"


def test_a_station_wins_over_an_id(client, search_ch):
    client.get("/v1/stationboard", params={"station": "Bern", "id": "8503000"})

    assert search_ch.last.url.params["stop"] == "Bern"


def test_without_a_stop_the_board_is_empty(client, search_ch):
    response = client.get("/v1/stationboard")

    assert response.status_code == 200
    assert response.json() == {"station": None, "stationboard": []}
    assert search_ch.requests == []


def test_a_limit_above_420_is_refused_in_plain_text(client, search_ch):
    """/v1 answers this one with a bare string, not the error envelope."""
    response = client.get("/v1/stationboard", params={"station": "Bern", "limit": "421"})

    assert response.status_code == 400
    assert response.text == "Invalid value for Parameter `limit`."
    assert search_ch.requests == []


def test_the_ceiling_itself_is_allowed(client, search_ch):
    search_ch.returns({"stop": None, "connections": []})

    response = client.get("/v1/stationboard", params={"station": "Bern", "limit": "420"})

    assert response.status_code == 200
    assert search_ch.last.url.params["limit"] == "420"


@pytest.mark.parametrize(
    ("spelling"),
    ["transportations[]", "transportations"],
)
def test_either_spelling_of_transportations_is_accepted(client, search_ch, spelling):
    """PHP folds `transportations[]` and `transportations` into one parameter."""
    search_ch.returns({"stop": None, "connections": []})

    client.get("/v1/stationboard", params=[("station", "Bern"), (spelling, "tram")])

    assert search_ch.last.url.params["transportation_types"] == "tram"


@pytest.mark.parametrize(
    ("transportations", "expected"),
    [
        (["tram", "bus"], "tram,bus"),
        # The old names are translated, and the duplicates that creates are
        # dropped - `ice_tgv_rj` and `ir` are both `train`.
        (["ice_tgv_rj", "ir", "bus"], "train,bus"),
        (["all"], None),
    ],
)
def test_transportations_are_translated_on_the_way_out(
    client, search_ch, transportations, expected
):
    search_ch.returns({"stop": None, "connections": []})
    client.get(
        "/v1/stationboard",
        params=[("station", "Bern")] + [("transportations[]", t) for t in transportations],
    )

    sent = search_ch.last.url.params
    if expected is None:
        assert "transportation_types" not in sent
    else:
        assert sent["transportation_types"] == expected


def test_a_prognosis_without_a_scheduled_time_is_dated_now(client, search_ch):
    """The quirk that cannot be compared between two requests, only within one.

    A departure board's head stop has no arrival time. /v1 still builds an
    arrival prognosis for it when the upstream sends `arr_delay`, and PHP reads
    the missing scheduled time as "now" - so the field carries the moment of
    the request. It is wrong, it is live, and it is reproduced.
    """
    search_ch.returns(
        {
            "stop": {"id": "8503000", "name": "Zürich HB"},
            "connections": [{"time": "2026-09-21 23:47:00", "arr_delay": "+0", "dep_delay": "+1"}],
        }
    )

    stop = client.get("/v1/stationboard", params={"station": "Bern"}).json()["stationboard"][0][
        "stop"
    ]

    assert stop["prognosis"]["arrival"] is not None
    assert stop["arrival"] is None
    # The departure prognosis, in contrast, is the scheduled time plus a minute.
    assert stop["prognosis"]["departure"] == "2026-09-21T23:48:00+0200"
    assert stop["delay"] == 1


def test_a_negative_delay_is_read_and_ignored(client, search_ch):
    """An early departure is announced as punctual, as in /v1."""
    search_ch.returns(
        {
            "stop": {"id": "1", "name": "Somewhere"},
            "connections": [{"time": "2026-09-21 23:47:00", "dep_delay": "-2"}],
        }
    )

    stop = client.get("/v1/stationboard", params={"station": "x"}).json()["stationboard"][0]["stop"]

    assert stop["prognosis"]["departure"] == "2026-09-21T23:47:00+0200"
    assert stop["delay"] == 0


def test_the_board_station_replaces_the_one_on_the_journeys_stop(client, search_ch):
    """But not the one in its passList - which is why they differ."""
    search_ch.returns(
        json.loads(json.dumps(fixture("stationboard/searchch_response_2016-12-23.json")))
    )

    journey = client.get("/v1/stationboard", params=PARAMS).json()["stationboard"][0]

    assert journey["stop"]["station"]["name"] == "Zürich HB"
    assert journey["passList"][0]["station"]["name"] is None


def test_a_prognosis_without_a_scheduled_time_still_gets_the_delay(client, search_ch):
    """ "Now plus the delay", not just "now".

    /v1 builds the date from a missing scheduled time - which PHP reads as the
    current moment - and then adds the delay to it anyway. So a departure
    board's head stop reports an arrival prognosis five minutes into the future
    of the request. Replaying real traffic is what showed it.
    """
    search_ch.returns(
        {
            "stop": {"id": "1", "name": "Somewhere"},
            "connections": [{"time": "2026-09-22 00:51:00", "arr_delay": "+5"}],
        }
    )

    stop = client.get("/v1/stationboard", params={"station": "x"}).json()["stationboard"][0]["stop"]

    prognosis = datetime.fromisoformat(stop["prognosis"]["arrival"])
    ahead = (prognosis - datetime.now(prognosis.tzinfo)).total_seconds()

    assert stop["arrival"] is None
    assert 4 * 60 < ahead <= 5 * 60 + 1, stop["prognosis"]["arrival"]
