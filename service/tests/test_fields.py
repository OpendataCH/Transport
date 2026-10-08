"""`fields[]` - the sparse-fieldset filter.

The trap the plan calls the single most likely thing to get subtly wrong, and
the one real traffic proved is in use: 788 of 41,176 requests in a ten-minute
slice of the live access log carry it. Every rule here was read off the live
API before it was written down.
"""

import pytest
from conftest import station

from transport_api.fields import Fields, NotAList, apply, tree_of

BERN = station("8507000", "Bern", 46.948832, 7.439131, icon="train")


def filtered(value, *paths):
    return apply(value, tree_of(list(paths)))


def test_without_fields_nothing_is_filtered():
    assert filtered({"a": 1, "b": {"c": 2}}) == {"a": 1, "b": {"c": 2}}


def test_a_path_keeps_its_branch_and_drops_the_rest():
    assert filtered({"a": {"b": 1, "c": 2}, "d": 3}, "a/b") == {"a": {"b": 1}}


def test_a_named_parent_keeps_everything_below_it():
    assert filtered({"a": {"b": 1, "c": 2}}, "a") == {"a": {"b": 1, "c": 2}}


def test_the_narrower_path_wins_over_the_broader_one():
    """`fields[]=stations&fields[]=stations/name` gives only the name.

    Read off the live API. The PHP merges the two into one subtree and the
    "keep everything" marker stops being reachable.
    """
    value = {"stations": [{"name": "Bern", "id": "8507000"}]}

    assert filtered(value, "stations", "stations/name") == {"stations": [{"name": "Bern"}]}


def test_lists_are_transparent():
    """A path names object keys; every entry of a list is reached alike."""
    value = {"board": [{"a": 1, "b": 2}, {"a": 3, "b": 4}]}

    assert filtered(value, "board/a") == {"board": [{"a": 1}, {"a": 3}]}


def test_an_object_that_loses_every_key_becomes_a_list():
    """`[]`, not `{}` - the PHP builds the filtered object in an array."""
    assert filtered({"a": 1}, "nonexistent") == []
    assert filtered({"a": {"b": 1}, "c": 2}, "a/zzz") == {"a": []}


def test_null_survives_being_asked_for():
    assert filtered({"a": None, "b": 1}, "a") == {"a": None}


def test_the_filter_reaches_into_a_real_answer(client, timetable):
    timetable.returns([BERN])

    body = client.get(
        "/v1/locations",
        params=[("query", "Be"), ("fields[]", "stations/name"), ("fields[]", "stations/icon")],
    ).json()

    assert body["stations"][0] == {"name": "Bern", "icon": "train"}


def test_a_field_nobody_has_empties_the_whole_document(client, timetable):
    timetable.returns([BERN])

    body = client.get("/v1/locations", params={"query": "Be", "fields[]": "nonexistent"}).json()

    assert body == []


def test_fields_without_brackets_is_a_bare_500(client, timetable):
    """What a TypeError escaping Silex looks like from outside: empty body."""
    response = client.get("/v1/locations", params={"query": "Be", "fields": "abc"})

    assert response.status_code == 500
    assert response.content == b""
    assert timetable.queries == []


def test_the_last_spelling_in_the_query_string_decides():
    """PHP's parse_str overwrites, so whichever comes last sets the type."""
    assert _fields_of("fields[]=a&fields[]=b").tree == {"a": True, "b": True}

    with pytest.raises(NotAList):
        _fields_of("fields[]=a&fields=b")


def _fields_of(query: str) -> Fields:
    from starlette.datastructures import QueryParams

    class FakeRequest:
        query_params = QueryParams(query)

    return Fields.of(FakeRequest())
