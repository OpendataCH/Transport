"""What every endpoint of /v1 writes the same way: the zone, the old names of
the means of transport, and PHP's formats for a moment and a duration.

The entities themselves are built in `timetable/mapping.py`.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

ZURICH = ZoneInfo("Europe/Zurich")

# The old transportation names, and what they mean now. /v1 accepts both and
# translates on the way out.
DEPRECATED_TYPES = {
    "ice_tgv_rj": "train",
    "ec_ic": "train",
    "ir": "train",
    "re_d": "train",
    "ship": "ship",
    "s_sn_r": "train",
    "bus": "bus",
    "cableway": "cableway",
    "arz_ext": "train",
    "tramway_underground": "tram",
    "tramway": "tram",
    "direct": "train",
    "direct_sleeper": "train",
    "direct_couchette": "train",
}


def iso(moment: datetime) -> str:
    """The format `/v1` emits: PHP's `DateTime::ISO8601`.

    `2016-12-23T14:30:00+0100` - note the offset without a colon. That constant
    predates RFC 3339 and is not quite ISO 8601 either, which is why it must be
    written out here rather than left to `isoformat()`.
    """
    return moment.strftime("%Y-%m-%dT%H:%M:%S%z")


def duration_of(seconds: int) -> str:
    """`00d00:43:00` - PHP's `gmdate("0z\\dH:i:s")`.

    A literal zero, then the day of the year (zero-based, so a duration under
    24 hours gives `0`), then `d`, then the clock. Two days look like `02d`;
    ten look like `010d`, because `z` is not padded. Nobody would design this,
    and it is what every client parses.
    """
    seconds = int(seconds)
    days, rest = divmod(seconds, 86400)
    hours, rest = divmod(rest, 3600)
    minutes, secs = divmod(rest, 60)
    return f"0{days}d{hours:02d}:{minutes:02d}:{secs:02d}"
