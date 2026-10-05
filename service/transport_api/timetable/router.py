"""The client of the router (MOTIS), shared by the routes that ask it."""

import httpx
from fastapi import Request

from .. import errors


class Motis:
    """The router, behind one HTTP client for the life of the process."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def plan(self, params: dict[str, str]) -> dict:
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
