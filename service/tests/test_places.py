"""Addresses and points of interest from the router's place search."""

import asyncio

from transport_api import errors
from transport_api.timetable import places


class Router:
    """The router's geocoder, answering what it is given - or failing."""

    def __init__(self, answer) -> None:
        self.answer = answer

    async def get(self, path, params):
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def street(name: str, number: str | None, town: str = "Aarburg", **extra) -> dict:
    return {
        "type": "ADDRESS",
        "street": name,
        "houseNumber": number,
        "zip": "4663",
        "lat": 47.32,
        "lon": 7.9,
        "areas": [{"name": town, "adminLevel": 8}],
        **extra,
    }


def run(coroutine):
    return asyncio.run(coroutine)


def test_a_router_that_fails_finds_nothing():
    router = Router(errors.ApiError(503, "down"))
    assert run(places.search(router, "Bern", ("address",))) == []
    assert run(places.nearest_address(router, 47.0, 7.0)) is None


def test_without_a_router_there_are_no_places():
    assert run(places.search(None, "Bern", ("address",))) == []
    assert run(places.nearest_address(None, 47.0, 7.0)) is None


def test_matches_without_a_position_or_of_another_kind_are_left_out():
    router = Router([street("Weberstrasse", "9", lat=None), {"type": "STOP", "lat": 1, "lon": 2}])
    assert run(places.search(router, "Weberstrasse", ("address",))) == []
    assert run(places.nearest_address(router, 47.0, 7.0)) is None


def test_an_address_needs_a_house_number():
    assert run(places.address(Router([street("Weberstrasse", "9")]), "Weberstrasse")) is None


def test_the_house_number_asked_for_wins():
    router = Router([street("Weberstrasse", "7"), street("Weberstrasse", "9")])
    assert run(places.address(router, "Weberstrasse 9, Aarburg")).house_number == "9"


def test_a_number_written_otherwise_still_finds_the_house():
    router = Router([street("Weberstrasse", "7"), street("Weberstrasse", "9.1")])
    assert run(places.address(router, "Weberstrasse 9, Aarburg")).house_number == "9.1"


def test_without_the_house_the_street_will_do():
    router = Router([street("Weberstrasse", "7")])
    assert run(places.address(router, "Weberstrasse 9, Aarburg")).house_number == "7"
    assert run(places.address(Router([]), "Weberstrasse 9, Aarburg")) is None


def test_a_town_without_a_municipality_falls_back_to_the_default_area():
    assert places._town([{"name": "Schweiz", "adminLevel": 2, "default": True}]) == "Schweiz"
    assert places._town([]) is None
