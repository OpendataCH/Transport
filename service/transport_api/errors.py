"""Errors in the shape /v1 uses: `{"errors": [{"message": …}]}`.

Same envelope, same status codes. An upstream 429 is passed through as 429,
because it is the caller's to retry and 8.3 % of production traffic is exactly
this; everything else the upstream does wrong becomes a 500 with a message
naming search.ch, exactly as the PHP application answers today.
"""

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError

from . import statistics
from .encoding import PhpErrorJson
from .fields import NotAList


class ApiError(Exception):
    """An error that is answered in the /v1 envelope."""

    def __init__(self, status_code: int, message: str, stats_exception: str | None = None) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.message = message
        # The class /stats.php counts this under, when the status alone does not say.
        self.stats_exception = stats_exception

    def response(self) -> PhpErrorJson:
        return PhpErrorJson(
            status_code=self.status_code,
            content={"errors": [{"message": self.message}]},
        )


# The messages are the PHP's, word for word, including the upstream body
# appended whole - untrimmed and untruncated. Two recorded fixtures assert
# exactly these strings, which is reason enough not to tidy them.
def rate_limited(detail: str) -> ApiError:
    return ApiError(429, f"Rate limit error from timetable.search.ch: {detail}")


def server_error(detail: str) -> ApiError:
    return ApiError(500, f"Server error from timetable.search.ch: {detail}")


def unreachable(detail: str) -> ApiError:
    """search.ch did not answer at all: the same 500 as server_error, counted apart."""
    return ApiError(
        500,
        f"Server error from timetable.search.ch: {detail}",
        stats_exception=statistics.REQUEST_EXCEPTION,
    )


def invalid_json(detail: str) -> ApiError:
    return ApiError(500, f"Invalid JSON from timetable.search.ch: {detail}")


def upstream_error(detail: str) -> ApiError:
    return ApiError(500, f"Error from timetable.search.ch: {detail}")


def install(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(request: Request, exc: ApiError) -> PhpErrorJson:
        if exc.stats_exception is not None:
            request.state.stats_exception = exc.stats_exception
        return exc.response()

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
