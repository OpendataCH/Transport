"""Writing JSON the way PHP writes it.

Structurally identical answers are not quite the same as identical answers. The
old implementation encodes with `json_encode`'s defaults, which differ from
every other language's in two visible ways:

- **non-ASCII is escaped**: `Zürich` goes out as `Z\\u00fcrich`;
- **forward slashes are escaped too**: a platform `43/44` goes out as `43\\/44`.

Both decode to the same string, so any client that parses JSON cannot tell the
difference. A client that matches on the raw bytes can - and this API's callers
are tens of thousands of unattended programs nobody can survey. On the day `/v1`
starts answering from here, the bytes should be the ones it has always sent.
"""

import json
import re
from typing import Any

from fastapi.responses import JSONResponse


class PhpJson(JSONResponse):
    """A JSON response encoded as `json_encode($value)` would encode it."""

    def render(self, content: Any) -> bytes:
        text = json.dumps(
            content,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )
        # With ensure_ascii the output is pure ASCII, and `/` can only occur
        # inside a string literal - JSON's own syntax has no use for it. So
        # escaping every one of them is safe without parsing.
        return text.replace("/", "\\/").encode("ascii")


# A JSON string literal, escapes included.
_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')
# Inside one: an escape pair, or a character PHP's HEX flags replace.
_HEX = re.compile(r"\\(.)|([<>&'])")
_HEX_OF = {'"': "\\u0022", "<": "\\u003C", ">": "\\u003E", "&": "\\u0026", "'": "\\u0027"}


def _hex(match: re.Match) -> str:
    escaped, bare = match.groups()
    if bare is not None:
        return _HEX_OF[bare]
    return _HEX_OF['"'] if escaped == '"' else "\\" + escaped


class PhpErrorJson(PhpJson):
    """An error envelope, encoded as Silex's `$app->json()` encodes it.

    The error handler and the validation answers of /v1 go through Symfony's
    JsonResponse, which adds JSON_HEX_TAG, JSON_HEX_APOS, JSON_HEX_AMP and
    JSON_HEX_QUOT to json_encode: `"` inside a string becomes `\\u0022`, `<`
    becomes `\\u003C`, and so on. It shows wherever a message quotes something
    - the rate-limit message carries search.ch's JSON body whole, and that is
    one answer in six.
    """

    def render(self, content: Any) -> bytes:
        text = super().render(content).decode("ascii")
        return _STRING.sub(lambda token: _HEX.sub(_hex, token.group(0)), text).encode("ascii")
