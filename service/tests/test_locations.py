"""`/v2/locations`, against the recorded search.ch answers."""

from conftest import fixture


def test_a_name_search_maps_each_entry(client, search_ch):
    search_ch.returns(fixture("locations/searchch_response.json"))

    body = client.get("/v2/locations", params={"query": "Be"}).json()

    assert body["locations"][0] == {
        "type": "station",
        "id": "8507000",
        "name": "Bern",
        # The degrees the upstream carries, not the ones /v1 computes from the
        # Swiss grid: those land about a metre away.
        "coordinate": {"lat": 46.948832, "lon": 7.439136},
        "distance": None,
        "category": "train",
    }
    assert [location["category"] for location in body["locations"][:3]] == [
        "train",
        "tram",
        "tram",
    ]


def test_the_term_and_the_flags_are_what_search_ch_needs(client, search_ch):
    client.get("/v2/locations", params={"query": "Be"})

    sent = search_ch.last.url.params
    assert sent["term"] == "Be"
    # Without these two the answer carries neither identifiers nor positions.
    assert sent["show_ids"] == "1"
    assert sent["show_coordinates"] == "1"
    assert "latlon" not in sent


def test_a_coordinate_search_asks_for_latlon_and_gets_distances(client, search_ch):
    search_ch.returns(fixture("locations/searchch_response_nearby.json"))

    body = client.get("/v2/locations", params={"lat": 47.002347, "lon": 8.379934}).json()

    assert search_ch.last.url.params["latlon"] == "47.002347,8.379934"
    assert body["locations"][0] == {
        "type": "address",
        "id": None,
        "name": "Hinterberg 4, Kehrsiten",
        # An address in the upstream answer carries no position at all.
        "coordinate": None,
        "distance": 9.0,
        "category": None,
    }
    assert body["locations"][1]["distance"] == 195.0


def test_an_address_is_an_address_and_not_a_station(client, search_ch):
    """The thing /v1 gets wrong by name.

    Its answer calls the whole list `stations`, addresses included. Here the
    kind is stated per entry, and `type=` narrows on it.
    """
    search_ch.returns(fixture("locations/searchch_response_nearby.json"))
    params = {"lat": 47.002347, "lon": 8.379934}

    addresses = client.get("/v2/locations", params=params | {"type": "address"}).json()
    stations = client.get("/v2/locations", params=params | {"type": "station"}).json()

    assert [location["type"] for location in addresses["locations"]] == ["address"]
    assert {location["type"] for location in stations["locations"]} == {"station"}
    assert len(addresses["locations"]) + len(stations["locations"]) == len(
        client.get("/v2/locations", params=params).json()["locations"]
    )


def test_an_entry_without_a_name_is_dropped(client, search_ch):
    search_ch.returns([{"id": "1", "iconclass": "sl-icon-type-bus"}])

    assert client.get("/v2/locations", params={"query": "x"}).json()["locations"] == []


def test_a_stop_lookup_may_be_cached_for_an_hour(client, search_ch):
    response = client.get("/v2/locations", params={"query": "Be"})

    assert response.headers["cache-control"] == "public, max-age=3600"


def test_asking_nothing_is_a_bad_request_not_an_empty_list(client, search_ch):
    """/v1 answers `{"stations": []}` here, which reads as "nothing found"."""
    response = client.get("/v2/locations")

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"].endswith("/invalid-parameters")
    assert search_ch.requests == []


def test_half_a_coordinate_is_a_bad_request(client, search_ch):
    response = client.get("/v2/locations", params={"lat": 47.0})

    assert response.status_code == 400
    assert "lat and lon" in response.json()["detail"]


def test_an_unknown_type_is_refused_in_the_same_shape(client, search_ch):
    """FastAPI would answer 422 with its own body; every error looks the same."""
    response = client.get("/v2/locations", params={"query": "Be", "type": "poi"})

    assert response.status_code == 400
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "type" in response.json()["detail"]
