"""The client of the router (MOTIS), shared by the routes that ask it."""

import asyncio
from contextlib import asynccontextmanager

import httpx
from fastapi import Request

from .. import errors, settings

# Journey plans each worker sends the router at once. The router is the one
# part of the service bound by the processor; a queue in front of it would
# only make every answer late. A plan that cannot start within
# MOTIS_QUEUE_SECONDS is refused with 429, as the API has always done when
# it had more to do than it could.
_plans: asyncio.Semaphore | None = None


def _plan_slots() -> asyncio.Semaphore:
    global _plans
    if _plans is None:
        _plans = asyncio.Semaphore(settings.MOTIS_CONCURRENCY)
    return _plans


@asynccontextmanager
async def plan_slot():
    """One of the worker's journey-plan slots, or 429 when none frees up in time."""
    slots = _plan_slots()
    try:
        await asyncio.wait_for(slots.acquire(), timeout=settings.MOTIS_QUEUE_SECONDS)
    except TimeoutError:
        raise errors.ApiError(
            429, "Rate limit error: too many requests at the moment, please try again."
        ) from None
    try:
        yield
    finally:
        slots.release()


class Motis:
    """The router, behind one HTTP client for the life of the process."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def plan(self, params: dict[str, str]) -> dict:
        async with plan_slot():
            return await self.get("/api/v6/plan", params)

    async def get(self, path: str, params: dict[str, str]) -> dict | list:
        """One call to the router's API; its failures in the /v1 envelope."""
        try:
            response = await self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise errors.ApiError(503, f"The router is not reachable: {exc}") from exc
        if response.status_code >= 400:
            raise errors.ApiError(
                503 if response.status_code >= 500 else 400,
                f"The router answered {response.status_code}: {response.text[:200]}",
            )
        return response.json()


def motis_or_none(request: Request) -> Motis | None:
    """The router when there is one: for what works without it, only better with it."""
    client = getattr(request.app.state, "motis", None)
    return Motis(client) if client is not None else None


def get_motis(request: Request) -> Motis:
    client = getattr(request.app.state, "motis", None)
    if client is None:
        raise errors.ApiError(503, "The router is not configured.")
    return Motis(client)
