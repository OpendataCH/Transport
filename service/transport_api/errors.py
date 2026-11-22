"""Errors in the shape /v1 uses: `{"errors": [{"message": …}]}`.

A 429 is the caller's to retry: the router is busy (timetable/router.py).
A 503 says the timetable or the router is not there.
"""

import asyncpg
from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError

from . import statistics
from .encoding import PhpErrorJson
from .fields import NotAList


class ApiError(Exception):
    """An error that is answered in the /v1 envelope."""

    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message

    def response(self) -> PhpErrorJson:
        return PhpErrorJson(
            status_code=self.status_code,
            content={"errors": [{"message": self.message}]},
        )


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> PhpErrorJson:
        return exc.response()

    @app.exception_handler(asyncpg.CharacterNotInRepertoireError)
    async def _no_text(_: Request, exc: asyncpg.CharacterNotInRepertoireError) -> PhpErrorJson:
        # A NUL in a parameter: Postgres takes it in no text, and no name has one.
        return ApiError(
            400, "A parameter contains a character that is not valid in text."
        ).response()

    @app.exception_handler(NotAList)
    async def _not_a_list(request: Request, exc: NotAList) -> Response:
        request.state.stats_exception = statistics.TYPE_ERROR
        # Empty body, text/html, 500 - what a TypeError escaping Silex looks
        # like from outside. See fields.NotAList.
        return Response(status_code=500, media_type="text/html; charset=UTF-8")

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> PhpErrorJson:
        # /v1 validates almost nothing and never answers 422. This is here so
        # that if a route ever does declare a constraint, what comes back is
        # still the one envelope every client already parses.
        detail = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'][1:])}: {error['msg']}"
            for error in exc.errors()
        )
        return ApiError(400, detail or "Invalid request.").response()
