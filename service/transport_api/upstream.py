"""The one address this whole service is about: timetable.search.ch.

Two things here are load-bearing.

**Identity forwarding.** search.ch applies its rate limiting to the caller we
name, so every request carries the caller's own IP address, their User-Agent
and - when they have one - their `key`. Lose that and every caller in the world
shares one bucket and throttles each other; the only symptom is a rise in 429s.
That is why it is a named type passed explicitly rather than something read
from a global.

**Error mapping.** The same as /v1: an upstream 429 is passed through as a
429, everything else becomes a 500 whose message names search.ch. /v2 answers
in the shape of /v1, error bodies included.
"""

from dataclasses import dataclass
from datetime import datetime

import httpx
from fastapi import Request

from . import errors, settings


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
            raise errors.server_error(
                f"Expected a list from completion.json, got {type(payload).__name__}."
            )
        return payload

    async def stationboard(
        self,
        *,
        stop: str,
        when: datetime,
        mode: str,
        limit: str,
        transportation_types: str | None,
        identity: ClientIdentity,
    ) -> dict:
        """`stationboard.json` - the departures or arrivals of one stop.

        The three `show_` flags are what make the answer usable: without them
        there are no platforms, no onward stops and no delays.
        """
        params = {
            "stop": stop,
            "date": when.strftime("%Y-%m-%d"),
            "time": when.strftime("%H:%M"),
            "mode": mode,
            "limit": limit,
            "show_tracks": "1",
            "show_subsequent_stops": "1",
            "show_delays": "1",
        }
        if transportation_types:
            params["transportation_types"] = transportation_types
        params.update(identity.fields())

        payload = await self._get("stationboard.json", params)
        if not isinstance(payload, dict):
            raise errors.server_error(
                f"Expected an object from stationboard.json, got {type(payload).__name__}."
            )
        return payload

    async def route(
        self,
        *,
        origin: str,
        destination: str,
        via: list[str],
        when: datetime,
        time_type: str,
        num: int | None,
        pre: int | None,
        transportation_types: str | None,
        identity: ClientIdentity,
    ) -> dict:
        """`route.json` - connections from one place to another.

        `num` asks for everything up to the end of the requested page and `pre`
        for results before the given time; /v1 then cuts its page out of the
        answer itself.
        """
        params = {
            "from": origin,
            "to": destination,
            "date": when.strftime("%Y-%m-%d"),
            "time": when.strftime("%H:%M"),
            "time_type": time_type,
            "show_delays": "1",
        }
        # Indexed, not repeated: the PHP flattens the array into via[0], via[1]
        # and so on, and search.ch reads it that way.
        for index, place in enumerate(via):
            params[f"via[{index}]"] = place
        if num is not None:
            params["num"] = str(num)
        if pre is not None:
            params["pre"] = str(pre)
        if transportation_types:
            params["transportation_types"] = transportation_types
        params.update(identity.fields())

        payload = await self._get("route.json", params)
        if not isinstance(payload, dict):
            raise errors.server_error(
                f"Expected an object from route.json, got {type(payload).__name__}."
            )
        return payload

    async def _get(self, path: str, params: dict[str, str]):
        try:
            response = await self._client.get(path, params=params)
        except httpx.TimeoutException as exc:
            # /v1 sets no timeout at all and would hold the worker until the
            # socket gives up. The answer is the same either way: a 500 naming
            # the upstream.
            raise errors.server_error(str(exc) or "No answer in time.") from exc
        except httpx.HTTPError as exc:
            raise errors.server_error(str(exc) or "The request failed.") from exc

        if response.status_code == 429:
            raise errors.rate_limited(response.text)
        if response.status_code >= 500:
            raise errors.server_error(f"{response.status_code} {response.reason_phrase}")

        try:
            payload = response.json()
        except ValueError as exc:
            raise errors.invalid_json(response.text) from exc

        # search.ch reports some failures in a 200 body.
        if isinstance(payload, dict) and payload.get("error"):
            raise errors.upstream_error(str(payload["error"]))

        return payload


def get_upstream(request: Request) -> Upstream:
    """The shared connection pool, as a seam a test can replace."""
    return Upstream(request.app.state.http)


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
