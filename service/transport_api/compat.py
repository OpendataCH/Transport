"""What /v1 does around the answers, rather than in them.

A comparison of every path and method against the live host on 24. September
2026 found these, none of which the JSON tests could see:

- **HEAD** is answered like GET, without a body. Silex matches a GET route for
  HEAD; FastAPI answers 405. Uptime monitors use HEAD.
- **Every answer carries `Access-Control-Allow-Origin: *`**, not only answers
  to a request with an `Origin` header, and `Cache-Control: no-cache`, which
  Symfony sets on anything that says nothing about caching.
- **An unknown path or method is answered in the error envelope**, with
  Symfony's wording: `No route found for "GET /v1/nothing"`.
- **A trailing slash is a different path** (404), not a redirect.

A path routing does not know may still be a file of the website (website.py);
only if it is not does the 404 go out.
"""

from fastapi import FastAPI, Request
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import website
from .encoding import PhpErrorJson

HEADERS = [(b"access-control-allow-origin", b"*"), (b"cache-control", b"no-cache")]


class PhpCompatMiddleware:
    """HEAD as GET, and the two headers every /v1 answer has."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        head = scope["method"] == "HEAD"
        if head:
            scope = dict(scope, method="GET")

        async def patched(message):
            if message["type"] == "http.response.start":
                present = {name.lower() for name, _ in message.get("headers", [])}
                extra = [(name, value) for name, value in HEADERS if name not in present]
                message = dict(message, headers=list(message.get("headers", [])) + extra)
            elif message["type"] == "http.response.body" and head:
                message = dict(message, body=b"", more_body=message.get("more_body", False))
            await send(message)

        await self.app(scope, receive, patched)


def install(app: FastAPI) -> None:
    app.router.redirect_slashes = False

    @app.exception_handler(StarletteHTTPException)
    async def _no_route(request: Request, exc: StarletteHTTPException):
        path = request.scope.get("path", "")
        if exc.status_code == 404:
            page = website.response_for(request)
            if page is not None:
                return page
            message = f'No route found for "{request.method} {path}"'
        elif exc.status_code == 405:
            message = (
                f'No route found for "{request.method} {path}": Method Not Allowed (Allow: GET)'
            )
        else:
            message = str(exc.detail)
        headers = {"allow": "GET"} if exc.status_code == 405 else None
        return PhpErrorJson(
            status_code=exc.status_code,
            content={"errors": [{"message": message}]},
            headers=headers,
        )
