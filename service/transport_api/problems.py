"""One shape for every error, and one place that decides the status code.

RFC 9457 problem details: `application/problem+json` with `type`, `title`,
`status` and `detail`. /v1 answers `{"errors": [{"message": …}]}` for its own
faults and something else again for a bad parameter; a client that wants to
tell "you asked wrongly" from "the upstream is throttling you" has to guess
from the status code alone. Here both are stated.
"""

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

CONTENT_TYPE = "application/problem+json"

# A stable, resolvable-looking identifier per kind of problem. It is what a
# client should branch on - the wording of `title` may change, these do not.
BASE = "https://transport.opendata.ch/problems/"


class Problem(Exception):
    """An error with a status, a kind and something to read."""

    def __init__(self, status_code: int, kind: str, title: str, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.kind = kind
        self.title = title
        self.detail = detail

    def response(self) -> JSONResponse:
        return JSONResponse(
            status_code=self.status_code,
            media_type=CONTENT_TYPE,
            content={
                "type": BASE + self.kind,
                "title": self.title,
                "status": self.status_code,
                "detail": self.detail,
            },
        )


def bad_request(detail: str) -> Problem:
    return Problem(
        status.HTTP_400_BAD_REQUEST,
        "invalid-parameters",
        "The request parameters do not make a question.",
        detail,
    )


def upstream_rate_limited(detail: str) -> Problem:
    """search.ch is throttling this caller.

    Passed through as 429 rather than dressed up as a fault of ours: it is
    8.3 % of production traffic on /v1, and a client that retries needs to know
    which side said no.
    """
    return Problem(
        status.HTTP_429_TOO_MANY_REQUESTS,
        "upstream-rate-limited",
        "search.ch is rate limiting this caller.",
        detail,
    )


def upstream_failed(detail: str) -> Problem:
    return Problem(
        status.HTTP_502_BAD_GATEWAY,
        "upstream-failed",
        "search.ch answered in a way this service cannot use.",
        detail,
    )


def upstream_timeout(detail: str) -> Problem:
    return Problem(
        status.HTTP_504_GATEWAY_TIMEOUT,
        "upstream-timeout",
        "search.ch did not answer in time.",
        detail,
    )


def install(app: FastAPI) -> None:
    """Route every error through the same shape, including FastAPI's own."""

    @app.exception_handler(Problem)
    async def _problem(_: Request, exc: Problem) -> JSONResponse:
        return exc.response()

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        # FastAPI would answer 422 with its own body. A wrong query parameter
        # is a bad request, and it gets the same shape as everything else.
        detail = "; ".join(
            f"{'.'.join(str(p) for p in error['loc'][1:])}: {error['msg']}"
            for error in exc.errors()
        )
        return bad_request(detail or "Invalid request.").response()
