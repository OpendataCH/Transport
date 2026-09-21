"""`/v2/locations`, against the answers /v1 is recorded to give.

The strongest test in the suite is the first one: the recorded search.ch
response goes in, and what comes out must equal the recorded /v1 output, key
for key. Those pairs are what the PHP suite asserts too, so a difference here
is a difference between the two implementations - not a matter of taste.
"""

import pytest
from conftest import fixture

from transport_api.models import LocationsResponse

PAIRS = [
    ("searchch_response.json", "response.json", {"query": "Be"}),
    (
        "searchch_response_nearby.json",
        "response_nearby.json",
        {"x": "47.002347", "y": "8.379934"},
    ),
    (
        "searchch_response_nyon.json",
        "response_nyon.json",
        {"x": "46.388653", "y": "6.238729"},
    ),
]


@pytest.mark.parametrize(("upstream", "expected", "params"), PAIRS)
def test_the_answer_is_the_one_v1_records(client, search_ch, upstream, expected, params):
    search_ch.returns(fixture(f"locations/{upstream}"))

    body = client.get("/v2/locations", params=params).json()

    assert body == fixture(f"locations/{expected}")


@pytest.mark.parametrize(("upstream", "expected", "params"), PAIRS)
def test_the_answer_matches_its_own_description(client, search_ch, upstream, expected, params):
    """The models exist for the OpenAPI document; this keeps them honest."""
    search_ch.returns(fixture(f"locations/{upstream}"))

    body = client.get("/v2/locations", params=params).json()

    LocationsResponse.model_validate(body)


def test_the_keys_are_in_the_order_v1_writes_them(client, search_ch):
    search_ch.returns(fixture("locations/searchch_response.json"))

    body = client.get("/v2/locations", params={"query": "Be"}).json()

    assert list(body["stations"][0]) == [
        "id",
        "name",
        "score",
        "coordinate",
        "distance",
        "icon",
    ]
    assert list(body["stations"][0]["coordinate"]) == ["type", "x", "y"]


def test_the_term_and_the_flags_are_what_search_ch_needs(client, search_ch):
    client.get("/v2/locations", params={"query": "Be"})

    sent = search_ch.last.url.params
    assert sent["term"] == "Be"
    # Without these two the answer carries neither identifiers nor positions.
    assert sent["show_ids"] == "1"
    assert sent["show_coordinates"] == "1"
    assert "latlon" not in sent


def test_a_coordinate_search_sends_latlon_in_that_order(client, search_ch):
    client.get("/v2/locations", params={"x": "47.002347", "y": "8.379934"})

    # x is the latitude. It reads backwards and it is the contract.
    assert search_ch.last.url.params["latlon"] == "47.002347,8.379934"


def test_an_entry_without_an_icon_class_has_no_icon_key(client, search_ch):
    """The "null versus missing" trap, in the flesh.

    /v1 only ever assigns `icon` when the upstream sends an icon class, so the
    key is absent rather than null. A client reading `location["icon"]` breaks
    on the difference; one reading `.get("icon")` does not. Both exist.
    """
    search_ch.returns([{"label": "Somewhere", "id": "1"}])

    station = client.get("/v2/locations", params={"query": "x"}).json()["stations"][0]

    assert "icon" not in station
    assert station["coordinate"] == {"type": "WGS84", "x": None, "y": None}


def test_an_unknown_icon_class_is_a_null_icon(client, search_ch):
    search_ch.returns([{"label": "Somewhere", "iconclass": "sl-icon-type-adr"}])

    station = client.get("/v2/locations", params={"query": "x"}).json()["stations"][0]

    assert station["icon"] is None


def test_an_address_is_its_own_class_and_carries_no_icon_at_all(client, search_ch):
    search_ch.returns(
        [{"label": "Bollwerk 19", "isaddress": True, "iconclass": "sl-icon-type-adr"}]
    )

    station = client.get("/v2/locations", params={"query": "x"}).json()["stations"][0]

    assert "icon" not in station
    assert station["id"] is None


def test_a_terminal_id_wins_over_the_entry_id(client, search_ch):
    """The PHP assigns the id three times in a row; the last one sticks."""
    search_ch.returns([{"label": "Somewhere", "id": "1", "stopid": "2", "terminal": {"id": "3"}}])

    station = client.get("/v2/locations", params={"query": "x"}).json()["stations"][0]

    assert station["id"] == "3"


def test_asking_nothing_answers_an_empty_list(client, search_ch):
    """Not a 400: a client with a half-filled form has always got this."""
    response = client.get("/v2/locations")

    assert response.status_code == 200
    assert response.json() == {"stations": []}
    assert search_ch.requests == []


@pytest.mark.parametrize("params", [{"x": "47.0"}, {"y": "8.3"}, {"x": "0", "y": "0"}])
def test_half_a_coordinate_asks_nothing(client, search_ch, params):
    """Including the `"0"` case, which PHP reads as absent."""
    assert client.get("/v2/locations", params=params).json() == {"stations": []}
    assert search_ch.requests == []


def test_the_type_parameter_is_accepted_and_ignored(client, search_ch):
    """As in /v1: the upstream completion endpoint has no type filter."""
    search_ch.returns(fixture("locations/searchch_response.json"))

    with_type = client.get("/v2/locations", params={"query": "Be", "type": "station"}).json()
    without = client.get("/v2/locations", params={"query": "Be"}).json()

    assert with_type == without
    assert "type" not in search_ch.last.url.params
