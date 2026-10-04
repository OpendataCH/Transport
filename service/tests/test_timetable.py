"""The timetable code that needs no database: reading the feed, times, shapes."""

import zipfile
from datetime import date, datetime, timedelta

import pytest
from gtfs_feed import CLOCKS_BACK, TODAY, write_feed

from transport_api.mapping import ZURICH
from transport_api.timetable import importer
from transport_api.timetable import stationboard as board
from transport_api.timetable.mapping import (
    journey_name,
    line_number,
    moment,
    prognosis,
    service_day_start,
    stop,
)
from transport_api.timetable.names import mode_of, normalize


def test_seconds_keep_times_past_midnight():
    assert importer.seconds("08:00:00") == 28800
    assert importer.seconds("25:10:00") == 90600


def test_service_days_apply_calendar_and_exceptions(tmp_path):
    with zipfile.ZipFile(write_feed(tmp_path)) as feed:
        days = importer.service_days(feed, TODAY, TODAY + timedelta(days=6))

    assert date(2026, 10, 6) not in days["daily"]  # removed by calendar_dates
    assert date(2026, 10, 5) in days["daily"]
    assert days["extra"] == [date(2026, 10, 7)]  # added, though not in calendar.txt
    assert days["sundays"] == [date(2026, 10, 11)]


def test_service_days_leave_out_services_without_a_day(tmp_path):
    with zipfile.ZipFile(write_feed(tmp_path)) as feed:
        days = importer.service_days(feed, TODAY, TODAY)  # a Monday

    assert "sundays" not in days
    assert "extra" not in days


def test_headway_trips_are_expanded_and_the_template_dropped(tmp_path):
    state = importer.Feed()
    with zipfile.ZipFile(write_feed(tmp_path)) as feed:
        state.stops = {r["stop_id"]: i for i, r in enumerate(importer.rows(feed, "stops.txt"))}
        state.trips = {
            "t-headway": importer.Trip(0, "t-headway", 0, 0, "Beta", "88", "bus"),
        }
        state.frequencies = {"t-headway": [(9 * 3600, 9 * 3600 + 1800, 600)]}
        records = list(importer.stop_time_records(feed, state))

    assert "t-headway" not in state.trips
    assert sorted(state.trips) == ["t-headway@32400", "t-headway@33000", "t-headway@33600"]
    departures = sorted(r[4] for r in records if r[1] == 1)
    assert departures == [32400, 33000, 33600]
    # The spacing between stops is the template's: five minutes.
    assert sorted(r[3] for r in records if r[1] == 2) == [32700, 33300, 33900]


def test_service_day_counts_from_noon_minus_twelve_hours():
    # An ordinary day starts at midnight ...
    assert service_day_start(TODAY) == datetime(2026, 10, 5, tzinfo=ZURICH)
    # ... and on the day the clocks go back, eight o'clock is still eight
    # o'clock, which counting from midnight would get wrong by an hour.
    eight = moment(CLOCKS_BACK, 8 * 3600)
    assert (eight.hour, eight.minute) == (8, 0)
    assert eight.utcoffset() == timedelta(hours=1)


def test_a_trip_past_midnight_lands_on_the_next_calendar_day():
    late = moment(TODAY, importer.seconds("24:10:00"))
    assert (late.date(), late.hour, late.minute) == (date(2026, 10, 6), 0, 10)


@pytest.mark.parametrize(
    ("route_type", "mode"),
    [
        (109, "train"),
        (102, "train"),
        (900, "tram"),
        (401, "tram"),
        (700, "bus"),
        (1000, "ship"),
        (1300, "cableway"),
        (1400, "cableway"),
        (1700, None),
    ],
)
def test_mode_of_extended_route_types(route_type, mode):
    assert mode_of(route_type) == mode


def test_normalize_folds_accents_and_case():
    assert normalize("  Genève,   Gare ") == "geneve, gare"
    assert normalize("Zürich HB") == "zurich hb"


def test_line_number_drops_the_category():
    assert line_number("S10", "S") == "10"
    assert line_number("IC1", "IC") == "1"
    assert line_number("10", "B") == "10"
    assert line_number("S", "S") == "S"


def test_journey_name_is_six_digits_wide():
    assert journey_name("15145") == "015145"
    assert journey_name("N1") == "N1"


def test_prognosis_moves_only_for_a_positive_delay():
    at = datetime(2026, 10, 5, 8, 0, tzinfo=ZURICH)
    now = datetime(2026, 10, 5, 7, 55, 30, tzinfo=ZURICH)
    late = prognosis(None, at, None, 3, now)
    early = prognosis(None, at, None, -2, now)
    assert late["departure"] == "2026-10-05T08:03:00+0200"
    assert early["departure"] == "2026-10-05T08:00:00+0200"
    assert late["arrival"] is None


def test_a_delay_without_a_scheduled_time_is_dated_now():
    # /v1's habit: the head stop of a board has no arrival, and an arrival
    # delay for it is added to the moment of the request.
    now = datetime(2026, 10, 5, 7, 55, 30, tzinfo=ZURICH)
    assert prognosis(None, None, 0, None, now)["arrival"] == "2026-10-05T07:55:30+0200"


def test_stop_delay_comes_from_the_prognosis():
    at = datetime(2026, 10, 5, 8, 0, tzinfo=ZURICH)
    now = at
    station = {"id": "8500001"}
    assert stop(station, None, at, "1", None, 4, now)["delay"] == 4
    assert stop(station, None, at, "1", None, None, now)["delay"] is None
    assert stop(station, None, at, "1", None, 0, now)["delay"] == 0


def test_cut_keeps_departures_in_the_minute_of_the_last():
    rows = [{"at": t} for t in (0, 60, 120, 125, 150, 180)]
    assert len(board._cut(rows, 3)) == 5
    assert len(board._cut(rows, 6)) == 6


def test_modes_translate_the_old_names():
    assert board._modes(["all"]) is None
    assert board._modes([]) is None
    assert board._modes(["ice_tgv_rj", "s_sn_r", "tramway"]) == ["train", "tram"]
    assert board._modes(["nonsense"]) is None
