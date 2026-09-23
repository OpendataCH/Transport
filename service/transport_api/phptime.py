"""The parts of PHP's date parsing that real clients lean on.

/v1 hands `date`, `time` and `datetime` to `strtotime()` or to the `DateTime`
constructor, and both read far more than ISO 8601. Measured on the live
traffic of 24. September 2026, three shapes matter that a plain ISO parser
refuses:

- **seconds with a fraction**, `00:46:30.077411` - what Home Assistant sends
  as `time` on every connection search, a good third of all of them;
- **day first**, `24.9.2026` and `24.9.2026 08:00`;
- **an offset** such as `Z` on a connection search, which `strtotime()`
  converts to local time rather than dropping.

Everything else `strtotime()` knows (`tomorrow`, `next monday`, ...) is not
sent by anyone and is left out on purpose.
"""

import re
from datetime import datetime

from .mapping import ZURICH

# What `strtotime()` returns for a string it cannot read is `false`, and
# `date('Y-m-d H:i', false)` is the epoch in Zurich time. /v1 sends exactly
# that to search.ch, so this does too.
EPOCH = datetime(1970, 1, 1, 1, 0, tzinfo=ZURICH)

_FRACTION = re.compile(r"(\d{1,2}:\d{2}:\d{2})\.\d+")

_PATTERNS = (
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y",
    "%H:%M:%S",
    "%H:%M",
)


def parse(value: str, reference: datetime, *, convert_offset: bool) -> datetime | None:
    """A moment in Zurich, or None when PHP would not have read it either.

    `reference` supplies the day for a bare time. `convert_offset` is the one
    place the two PHP readers differ: `strtotime()` moves a time with an offset
    into local time, while `new DateTime($s, $zurich)` keeps the wall clock the
    string names.
    """
    value = _FRACTION.sub(r"\1", value.strip())
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        parsed = None
    if parsed is not None:
        if parsed.tzinfo is not None and convert_offset:
            return parsed.astimezone(ZURICH)
        return parsed.replace(tzinfo=ZURICH)

    for pattern in _PATTERNS:
        try:
            parsed = datetime.strptime(value, pattern)
        except ValueError:
            continue
        if pattern.startswith("%H"):
            parsed = parsed.replace(year=reference.year, month=reference.month, day=reference.day)
        return parsed.replace(tzinfo=ZURICH)
    return None
