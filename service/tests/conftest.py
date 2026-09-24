"""Test fixtures, including the recorded search.ch answers.

`fixtures/` holds recorded search.ch answers paired with the answer /v1 gave
to each - the corpus the PHP suite was built on, and the proof that this
service answers as that implementation did.
"""

import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from transport_api import settings
from transport_api import upstream as upstream_module
from transport_api.main import app
from transport_api.upstream import Upstream

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def fixture(name: str):
    """Read a recorded upstream answer, e.g. `locations/searchch_response.json`."""
    return json.loads((FIXTURES / name).read_text())


class FakeSearchCh:
    """search.ch, replaced by something that answers on command and remembers.

    It is an `httpx.MockTransport`, so the code under test still builds a real
    request - which is how the tests can assert what was actually sent.
    """

    def __init__(self) -> None:
        self.requests: list[httpx.Request] = []
        self._respond = lambda request: httpx.Response(200, json=[])
        self._client = httpx.AsyncClient(
            base_url=settings.UPSTREAM_URL,
            transport=httpx.MockTransport(self._handle),
        )

    def returns(self, payload, status_code: int = 200) -> None:
        self._respond = lambda request: httpx.Response(status_code, json=payload)

    def returns_text(self, text: str, status_code: int = 200) -> None:
        self._respond = lambda request: httpx.Response(status_code, text=text)

    def raises(self, error: Exception) -> None:
        def respond(request: httpx.Request) -> httpx.Response:
            raise error

        self._respond = respond

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return self._respond(request)

    @property
    def last(self) -> httpx.Request:
        assert self.requests, "nothing was sent upstream"
        return self.requests[-1]

    def upstream(self) -> Upstream:
        return Upstream(self._client)


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def search_ch():
    fake = FakeSearchCh()
    app.dependency_overrides[upstream_module.get_upstream] = fake.upstream
    yield fake
    app.dependency_overrides.clear()
