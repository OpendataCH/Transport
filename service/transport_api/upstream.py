"""The one address this whole service is about: timetable.search.ch.

Two things here are load-bearing.

**Identity forwarding.** search.ch applies its rate limiting to the caller we
name, so every request carries the caller's own IP address, their User-Agent
and - when they have one - their `key`. Lose that and every caller in the world
shares one bucket and throttles each other; the only symptom is a rise in 429s.
That is why it is a named type passed explicitly rather than something read
from a global.

**Error mapping.** An upstream 429 stays a 429, because it is the caller's
problem to retry. Everything else the upstream does wrong becomes a 502 or a
504 - never a 500, which would claim the fault is here.
"""

from dataclasses import dataclass

import httpx
from fastapi import Request

from . import problems, settings


@dataclass(frozen=True)
class ClientIdentity:
    """Who is asking, as far as search.ch is concerned."""

    ip_address: str | None
    user_agent: str | None
    key: str | None

    @classmethod
    def of(cls, request: Request) -> "ClientIdentity":
        # request.client is set from X-Forwarded-For by uvicorn's proxy-headers
        # handling; the container is never reached except through nginx.
        return cls(
            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            key=request.query_params.get("key"),
        )

    def fields(self) -> dict[str, str]:
        fields = {}
        if self.ip_address:
            fields["ip_address"] = self.ip_address
        if self.user_agent:
            fields["user_agent"] = self.user_agent
        if self.key:
            fields["key"] = self.key
        return fields


class Upstream:
    """A thin, typed front for the search.ch endpoints this service uses."""

    def __init__(self, client: httpx.AsyncClient) -> None:
        self._client = client

    async def completion(
        self,
        *,
        term: str | None,
        latlon: str | None,
        identity: ClientIdentity,
    ) -> list[dict]:
        """`completion.json` - the location search.

        `show_ids` and `show_coordinates` are not optional for us: without them
        the answer carries neither stop identifiers nor positions.
        """
        params: dict[str, str] = {
            "term": term or "",
            "show_ids": "1",
            "show_coordinates": "1",
        }
        if latlon:
            params["latlon"] = latlon
        params.update(identity.fields())

        payload = await self._get("completion.json", params)
        if not isinstance(payload, list):
            raise problems.upstream_failed(
                f"Expected a list from completion.json, got {type(payload).__name__}."
            )
        return payload

    async def _get(self, path: str, params: dict[str, str]):
        try:
            response = await self._client.get(path, params=params)
        except httpx.TimeoutException as exc:
            raise problems.upstream_timeout(str(exc) or "No answer in time.") from exc
        except httpx.HTTPError as exc:
            raise problems.upstream_failed(str(exc) or "The request failed.") from exc

        if response.status_code == 429:
            raise problems.upstream_rate_limited(response.text.strip()[:200])
        if response.status_code >= 500:
            raise problems.upstream_failed(f"{response.status_code} {response.reason_phrase}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise problems.upstream_failed(f"Invalid JSON: {response.text.strip()[:200]}") from exc

        # search.ch reports some failures in a 200 body.
        if isinstance(payload, dict) and payload.get("error"):
            raise problems.upstream_failed(str(payload["error"])[:200])

        return payload


def build_client() -> httpx.AsyncClient:
    """The long-lived connection pool, one per process."""
    return httpx.AsyncClient(
        base_url=settings.UPSTREAM_URL,
        timeout=httpx.Timeout(settings.UPSTREAM_TIMEOUT, connect=5.0),
        # The caller's User-Agent is forwarded in a field, not in the header,
        # exactly as /v1 does it; the header names this service so that
        # search.ch can tell us apart in their logs.
        headers={"User-Agent": f"transport.opendata.ch/{settings.VERSION}"},
        follow_redirects=True,
    )
