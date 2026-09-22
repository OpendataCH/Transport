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
