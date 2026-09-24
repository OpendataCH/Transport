"""The website around the API: the landing page, the documentation, the examples.

Static files in `site/`, served as Apache served them from the PHP
application's `web/` directory: a directory answers with its `index.html`, a
directory asked for without its trailing slash is redirected to it, and
anything that is not a file gets the API's own 404 in the error envelope.
`/swagger.json` is one of the files: the PHP application generated it from
annotations that no longer change, so it is kept as the document it produced.

The one PHP page among the examples, `connections.php`, is now
`connections.html` and does its work in the browser; the old address redirects
there, query string and all.

The files are looked up only once routing has found nothing (see compat.py),
not by a catch-all route: a catch-all would turn a POST to an unknown path into
a 405, where /v1 has always answered 404.

None of this is the API, so none of it is counted for the statistics page.
"""

import mimetypes
from pathlib import Path

from fastapi import Request
from fastapi.responses import FileResponse, RedirectResponse, Response

SITE = (Path(__file__).parent / "site").resolve()

# What Apache called these; Python's table differs or lacks them.
MEDIA_TYPES = {
    ".html": "text/html",
    ".ico": "image/vnd.microsoft.icon",
    ".json": "application/json",
}

# Old addresses of pages that moved, relative to the site root.
MOVED = {"examples/connections.php": "/examples/connections.html"}


def response_for(request: Request) -> Response | None:
    """The website's answer to a GET routing found nothing for, or None."""
    if request.method != "GET":
        return None

    path = request.url.path.lstrip("/")
    query = request.url.query
    suffix = f"?{query}" if query else ""

    if path in MOVED:
        return _uncounted(request, RedirectResponse(MOVED[path] + suffix, status_code=301))

    target = (SITE / path).resolve()
    if not target.is_relative_to(SITE):
        return None

    if target.is_dir():
        if path and not path.endswith("/"):
            return _uncounted(request, RedirectResponse(f"/{path}/{suffix}", status_code=301))
        target = target / "index.html"

    if not target.is_file():
        return None

    media_type = MEDIA_TYPES.get(target.suffix) or mimetypes.guess_type(target.name)[0]
    return _uncounted(
        request, FileResponse(target, media_type=media_type or "application/octet-stream")
    )


def _uncounted(request: Request, response: Response) -> Response:
    request.state.stats_skip = True
    return response
