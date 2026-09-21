"""`/v2/connections`, against the answers /v1 is recorded to give.

Four recorded pairs: three journeys and two failures. The failures matter as
much as the journeys - they pin the error envelope and the exact wording, which
is what a client that has learned to read it will be matching on.
"""

import pytest
from conftest import fixture

from transport_api.models import ConnectionsResponse

PAIRS = [
    (
        "searchch_response_2016-12-23.json",
        "response_2016-12-23.json",
        {"from": "Zürich", "to": "Bern", "date": "2016-12-23", "time": "14:30:00"},
    ),
    (
        "searchch_response_2017-06-20.json",
        "response_2017-06-20.json",
        {"from": "Zürich HB", "to": "Olten", "date": "2017-06-20", "time": "22:30:00"},
    ),
    (
        "searchch_response_2021-11-01.json",
        "response_2021-11-01.json",
        {"from": "Zürich", "to": "Bern", "date": "2021-11-01", "time": "14:30:00"},
    ),
]


@pytest.mark.parametrize(("upstream", "expected", "params"), PAIRS)
def test_the_answer_is_the_one_v1_records(client, search_ch, upstream, expected, params):
    search_ch.returns(fixture(f"connections/{upstream}"))

    body = client.get("/v2/connections", params=params).json()

    assert body == fixture(f"connections/{expected}")


@pytest.mark.parametrize(("upstream", "expected", "params"), PAIRS)
def test_the_answer_matches_its_own_description(client, search_ch, upstream, expected, params):
    search_ch.returns(fixture(f"connections/{upstream}"))

    body = client.get("/v2/connections", params=params).json()

    ConnectionsResponse.model_validate(body)


def test_an_error_in_the_body_is_reported_word_for_word(client, search_ch):
    """The recorded failure, including the sentence search.ch sent."""
    search_ch.returns(fixture("connections/searchch_response_error.json"))

    response = client.get("/v2/connections", params={"from": "Zürich", "to": "Bern"})

    assert response.status_code == 500
    assert response.json() == fixture("connections/response_error.json")


def test_a_body_that_is_not_json_is_reported_whole(client, search_ch):
    """Untrimmed, trailing newline and all - as the recorded answer has it."""
    search_ch.returns_text("500 Internal Server Error\n")

    response = client.get("/v2/connections", params={"from": "Zürich", "to": "Bern"})

    assert response.status_code == 500
    assert response.json() == fixture("connections/response_500.json")


def test_the_keys_are_in_the_order_v1_writes_them(client, search_ch):
    search_ch.returns(fixture("connections/searchch_response_2016-12-23.json"))

    body = client.get("/v2/connections", params=PAIRS[0][2]).json()

    assert list(body) == ["connections", "from", "to", "stations"]
    assert list(body["connections"][0]) == [
        "from",
        "to",
        "duration",
        "transfers",
        "service",
        "products",
        "capacity1st",
        "capacity2nd",
        "sections",
    ]
    assert list(body["connections"][0]["sections"][0]) == [
        "journey",
        "walk",
        "departure",
        "arrival",
    ]


def test_the_upstream_is_asked_the_way_v1_asks(client, search_ch):
    search_ch.returns(fixture("connections/searchch_response_2016-12-23.json"))

    client.get("/v2/connections", params=PAIRS[0][2])

    sent = search_ch.last.url.params
    assert sent["from"] == "Zürich"
    assert sent["to"] == "Bern"
    assert sent["date"] == "2016-12-23"
    assert sent["time"] == "14:30"
    assert sent["time_type"] == "departure"
    assert sent["show_delays"] == "1"
    # One page of four, so four results are asked for.
    assert sent["num"] == "4"
    assert "pre" not in sent


def test_via_is_sent_indexed_not_repeated(client, search_ch):
    search_ch.returns({"connections": []})

    client.get(
        "/v2/connections",
        params=[("from", "Bern"), ("to", "Genève"), ("via[]", "Fribourg"), ("via[]", "Lausanne")],
    )

    sent = search_ch.last.url.params
    assert sent["via[0]"] == "Fribourg"
    assert sent["via[1]"] == "Lausanne"


def test_an_arrival_search_looks_one_page_back(client, search_ch):
    """Asking for arrivals shifts the window, as in /v1."""
    search_ch.returns({"connections": []})

    client.get(
        "/v2/connections",
        params={"from": "Bern", "to": "Genève", "isArrivalTime": "1"},
    )

    sent = search_ch.last.url.params
    assert sent["time_type"] == "arrival"
    # Page 0 becomes page -1, and a negative page asks for results *before*
    # the given time instead of after it.
    assert sent["pre"] == "4"
    assert "num" not in sent


def test_a_later_page_asks_for_everything_up_to_it(client, search_ch):
    search_ch.returns({"connections": []})

    client.get(
        "/v2/connections", params={"from": "Bern", "to": "Genève", "page": "2", "limit": "3"}
    )

    assert search_ch.last.url.params["num"] == "9"


def test_the_page_is_cut_out_of_what_came_back(client, search_ch):
    search_ch.returns({"connections": [{"duration": i, "legs": []} for i in range(9)]})

    body = client.get(
        "/v2/connections", params={"from": "Bern", "to": "Genève", "page": "2", "limit": "3"}
    ).json()

    assert [connection["duration"] for connection in body["connections"]] == [
        "00d00:00:06",
        "00d00:00:07",
        "00d00:00:08",
    ]


def test_the_offset_is_clamped_into_the_first_sixteen(client, search_ch):
    """A high page with a high limit returns the tail of the window, not nothing."""
    search_ch.returns({"connections": [{"duration": i, "legs": []} for i in range(16)]})

    body = client.get(
        "/v2/connections", params={"from": "Bern", "to": "Genève", "page": "9", "limit": "10"}
    ).json()

    assert [connection["duration"] for connection in body["connections"]][0] == "00d00:00:06"


@pytest.mark.parametrize(
    ("params", "message"),
    [
        ({"limit": "17"}, "Maximal value of argument `limit` is 16."),
        ({"page": "11"}, "Maximal value of argument `page` is 10."),
    ],
)
def test_a_parameter_out_of_range_is_a_list_of_sentences(client, search_ch, params, message):
    """A different error shape from the exception envelope, and both are live."""
    response = client.get("/v2/connections", params={"from": "Bern", "to": "Genève", **params})

    assert response.status_code == 400
    assert response.json() == {"errors": [message]}
    assert search_ch.requests == []


def test_more_than_five_vias_are_refused(client, search_ch):
    response = client.get(
        "/v2/connections",
        params=[("from", "Bern"), ("to", "Genève")] + [("via[]", place) for place in "abcdef"],
    )

    assert response.status_code == 400
    assert response.json() == {"errors": ["Invalid via count (max 5 allowed)."]}


def test_without_both_ends_the_answer_is_the_empty_one(client, search_ch):
    response = client.get("/v2/connections", params={"from": "Bern"})

    assert response.status_code == 200
    assert response.json() == {
        "connections": [],
        "from": None,
        "to": None,
        "stations": {"from": [], "to": []},
    }
    assert search_ch.requests == []


def test_the_parameters_that_do_nothing_still_do_nothing(client, search_ch):
    """`direct`, `sleeper`, `couchette`, `bike`, `accessibility`.

    They only ever reached the HAFAS request, which is no longer made. /v1
    accepts them in silence, so answering anything else would be a change.
    """
    search_ch.returns({"connections": []})

    response = client.get(
        "/v2/connections",
        params={
            "from": "Bern",
            "to": "Genève",
            "direct": "1",
            "sleeper": "1",
            "couchette": "1",
            "chouchette": "1",
            "bike": "1",
            "accessibility": "independent_boarding",
        },
    )

    assert response.status_code == 200
    sent = search_ch.last.url.params
    assert not [name for name in sent if name in ("direct", "sleeper", "bike", "accessibility")]


def test_a_repeated_via_without_brackets_keeps_only_the_last(client, search_ch):
    """PHP's parse_str overwrites, so `via=a&via=b&via=c` is just `c`.

    Found by replaying real traffic: a client sends three unbracketed vias, and
    reading them as a list of three routed the journey somewhere else entirely
    - a different destination in the answer, not a subtle field.
    """
    search_ch.returns({"connections": []})

    client.get(
        "/v2/connections",
        params=[
            ("from", "Machilly"),
            ("to", "Genève-Champel"),
            ("via", "Annemasse"),
            ("via", "Chêne-bourg"),
            ("via", "Eaux-vives"),
        ],
    )

    sent = search_ch.last.url.params
    assert sent["via[0]"] == "Eaux-vives"
    assert "via[1]" not in sent


def test_a_repeated_transportations_without_brackets_does_the_same(client, search_ch):
    search_ch.returns({"connections": []})

    client.get(
        "/v2/connections",
        params=[
            ("from", "Bern"),
            ("to", "Genève"),
            ("transportations", "bus"),
            ("transportations", "tram"),
        ],
    )

    assert search_ch.last.url.params["transportation_types"] == "tram"


def test_an_empty_platform_stays_an_empty_string(client, search_ch):
    """`isset`, not truthiness.

    search.ch sends `"track": ""` for a stop with no platform. /v1 copies it
    onto the connection's arrival, so the field is an empty string there and
    null everywhere else. Found by replaying real traffic.
    """
    search_ch.returns(
        {
            "connections": [
                {
                    "duration": 60,
                    "legs": [
                        {"departure": "2026-09-24 09:00:00", "type": "bus", "exit": {"track": ""}},
                        {"arrival": "2026-09-24 09:01:00"},
                    ],
                }
            ]
        }
    )

    body = client.get("/v2/connections", params={"from": "a", "to": "b"}).json()

    assert body["connections"][0]["to"]["platform"] == ""
