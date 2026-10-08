"""The clients of the router and of the timetable database: their failures,
in the /v1 envelope."""

import asyncio
from typing import Annotated

import asyncpg
import httpx
import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from transport_api import errors, settings
from transport_api.timetable import db, router


def motis(respond) -> router.Motis:
    client = httpx.AsyncClient(base_url="http://motis", transport=httpx.MockTransport(respond))
    return router.Motis(client)


def ask(m: router.Motis):
    return asyncio.run(m.get("/api/v6/plan", {}))


def test_an_answer_is_its_json():
    assert ask(motis(lambda request: httpx.Response(200, json={"ok": 1}))) == {"ok": 1}


def test_a_router_that_does_not_answer_is_a_503():
    def respond(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(errors.ApiError) as caught:
        ask(motis(respond))
    assert caught.value.status_code == 503
    assert "not reachable" in caught.value.message


@pytest.mark.parametrize(("status", "expected"), [(500, 503), (400, 400), (404, 400)])
def test_a_refusal_of_the_router_keeps_its_side(status, expected):
    with pytest.raises(errors.ApiError) as caught:
        ask(motis(lambda request: httpx.Response(status, text="nope")))
    assert caught.value.status_code == expected
    assert f"answered {status}" in caught.value.message


def test_without_a_router_connections_say_so():
    app = FastAPI()
    errors.install(app)

    @app.get("/plan")
    def plan(m: Annotated[router.Motis, Depends(router.get_motis)]):  # pragma: no cover
        return {}

    @app.get("/places")
    def places(m: Annotated[router.Motis | None, Depends(router.motis_or_none)]):
        return {"router": m is not None}

    with TestClient(app) as client:
        answer = client.get("/plan")
        assert answer.status_code == 503
        assert answer.json() == {"errors": [{"message": "The router is not configured."}]}
        assert client.get("/places").json() == {"router": False}


class Pool:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def fetch(self, query, *args):
        raise self.error


@pytest.mark.parametrize(
    ("error", "message"),
    [
        (asyncpg.UndefinedTableError("no table"), "has not been loaded yet"),
        (OSError("refused"), "is not reachable"),
    ],
)
def test_the_timetable_database_fails_in_the_envelope(error, message):
    with pytest.raises(errors.ApiError) as caught:
        asyncio.run(db.fetch(Pool(error), "SELECT 1"))
    assert caught.value.status_code == 503
    assert message in caught.value.message


def test_without_a_database_url_there_is_no_pool(monkeypatch):
    monkeypatch.setattr(settings, "DATABASE_URL", None)
    assert asyncio.run(db.connect()) is None


def test_the_api_asks_the_database_without_parallel_plans(monkeypatch):
    """Parallel workers of many boards at once exhaust Postgres' shared memory."""
    made = {}

    async def create_pool(url, **options):
        made.update(options, url=url)
        return "pool"

    monkeypatch.setattr(settings, "DATABASE_URL", "postgresql://db/transport")
    monkeypatch.setattr(db.asyncpg, "create_pool", create_pool)
    assert asyncio.run(db.connect()) == "pool"
    assert made["server_settings"] == {"max_parallel_workers_per_gather": "0"}
