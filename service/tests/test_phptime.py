"""Dates and times the way /v1 reads them - checked against PHP itself.

Every expected value below is what PHP 8 prints for the same input, run on
24. September 2026 with the zone set to Europe/Zurich. The shapes are the ones
measured in the live traffic of that day; the first is a third of all
connection searches.
"""

from datetime import datetime

import pytest

from transport_api.mapping import ZURICH
from transport_api.timetable import connections, stationboard

DAY = datetime(2026, 9, 25, 12, 0, tzinfo=ZURICH)


def fmt(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%d %H:%M")


@pytest.mark.parametrize(
    "combined, date, time, expected",
    [
        # Home Assistant: seconds with six decimals.
        (None, "2026-09-25", "00:46:30.077411", "2026-09-25 00:46"),
        (None, "2026-10-01", "07:05:59.9", "2026-10-01 07:05"),
        (None, "2026-09-24 00:00", "00:08:37.2500000", "2026-09-24 00:08"),
        (None, "2026-09-25", "23:59:59.999999", "2026-09-25 23:59"),
        # Day first.
        (None, "01.10.2026", "7:05", "2026-10-01 07:05"),
        # strtotime() moves an offset into local time.
        ("2026-12-01T06:00:00Z", None, None, "2026-12-01 07:00"),
        ("2026-09-23T21:59:06.551Z", None, None, "2026-09-23 23:59"),
        ("2026-12-01T06:00:00.123+01:00", None, None, "2026-12-01 06:00"),
        # What it cannot read is false, and false is the epoch.
        ("garbage", None, None, "1970-01-01 01:00"),
        (None, "not-a-date", "08:00", "1970-01-01 08:00"),
        # A comma is not a decimal point to PHP.
        (None, "2026-09-30", "13:15:00,5", "2026-09-30 01:00"),
    ],
)
def test_connections_read_the_time_as_strtotime_does(combined, date, time, expected):
    assert fmt(connections._when(combined, date, time)) == expected


@pytest.mark.parametrize(
    "given, expected",
    [
        ("2026-09-24T01:36:40.123456", "2026-09-24 01:36"),
        ("25.9.2026 08:00", "2026-09-25 08:00"),
        ("1.10.2026", "2026-10-01 00:00"),
        # new DateTime() keeps the wall clock of an offset.
        ("2026-12-01T06:00:00Z", "2026-12-01 06:00"),
        ("2026-09-14T10:00:00+0200", "2026-09-14 10:00"),
    ],
)
def test_the_board_reads_the_time_as_datetime_does(given, expected):
    assert fmt(stationboard.moment_of(given)) == expected


def test_a_bare_time_with_a_fraction_is_today():
    moment = stationboard.moment_of("13:15:00.25")
    today = datetime.now(ZURICH)

    assert (moment.date(), moment.hour, moment.minute) == (today.date(), 13, 15)
