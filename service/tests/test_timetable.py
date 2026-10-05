"""The timetable code that needs no database: reading the feed, times, shapes."""

import zipfile
from datetime import date, datetime, timedelta

import pytest
from gtfs_feed import CLOCKS_BACK, TODAY, write_feed

from transport_api.mapping import ZURICH
from transport_api.timetable import importer
from transport_api.timetable import stationboard as board
from transport_api.timetable.mapping import (
    destination,
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


def test_normalize_folds_accents_case_and_punctuation():
    assert normalize("  Genève,   Gare ") == "geneve gare"
    assert normalize("Zürich HB") == "zurich hb"
    assert normalize("Luzern, Verkehrshaus") == normalize("Luzern Verkehrshaus")
    assert normalize("Biel/Bienne") == "biel bienne"


def test_normalize_abbreviates_saint_as_the_stops_do():
    assert normalize("Sainte-Croix") == normalize("Ste-Croix") == "ste croix"
    assert normalize("Saint-Cergue") == normalize("St-Cergue")
    assert normalize("Sankt Gallen") == normalize("St. Gallen")


def test_line_number_drops_the_category():
    assert line_number("S10", "S", "12824") == "10"
    assert line_number("IC1", "IC", "719") == "1"
    assert line_number("10", "B", "2001") == "10"


def test_a_train_without_a_line_is_numbered_by_its_train_number():
    assert line_number("ICE", "ICE", "271") == "000271"
    assert line_number("S", "S", None) == "S"


def test_a_splitting_train_is_named_by_its_first_destination():
    assert destination("Neuchâtel | Avenches") == "Neuchâtel"
    assert destination("Bern") == "Bern"
    assert destination(None) is None


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


def test_window_feed_keeps_whole_trips_of_the_window_only(tmp_path):
    source = write_feed(tmp_path)
    target = tmp_path / "window.zip"
    # Monday to Wednesday: no Sunday, and "extra" runs on the Wednesday.
    counts = importer.write_window_feed(source, target, TODAY, TODAY + timedelta(days=2))

    with zipfile.ZipFile(target) as feed:
        trips = {r["trip_id"] for r in importer.rows(feed, "trips.txt")}
        stop_times = list(importer.rows(feed, "stop_times.txt"))
        stops = list(importer.rows(feed, "stops.txt"))

    assert trips == {"t-morning", "t-night", "t-extra", "t-headway"}
    # Every stop time of a kept trip is kept; the Sunday trip's are gone.
    assert sum(r["trip_id"] == "t-morning" for r in stop_times) == 3
    assert not any(r["trip_id"] == "t-sunday" for r in stop_times)
    # Stops are not cut, and the frequencies of kept trips stay.
    assert len(stops) == 6
    assert counts["frequencies.txt"] == 1


def test_publish_window_points_the_router_at_it(tmp_path):
    source = write_feed(tmp_path)
    window = importer.build_window([source], tmp_path, TODAY, TODAY + timedelta(days=14))
    importer.publish_window(window)
    assert window.name == "window_20261001_20261005_walks.zip"
    assert (tmp_path / "CURRENT").read_text().strip() == window.name


def _year_feeds(tmp_path):
    """This year's test feed ending on 12 December, and next year's from the 13th.

    Next year's reuses the calendar ids and a route id, renames a stop, and
    carries its own trip ids, as the Swiss feeds do.
    """
    import gtfs_feed

    this = dict(gtfs_feed.FILES)
    this["feed_info.txt"] = this["feed_info.txt"].replace("20261231", "20261212")
    nxt = {
        name: text.replace('"t-', '"n-')
        .replace("20260101", "20261213")
        .replace("20261231", "20271211")
        for name, text in gtfs_feed.FILES.items()
    }
    nxt["stops.txt"] = nxt["stops.txt"].replace('"Beta"', '"Beta Neu"')
    nxt["feed_info.txt"] = nxt["feed_info.txt"].replace('"20261001"', '"20261101"')
    paths = []
    for name, files in (("gtfs_fp2026.zip", this), ("gtfs_fp2027.zip", nxt)):
        path = tmp_path / name
        with zipfile.ZipFile(path, "w") as archive:
            for filename, text in files.items():
                archive.writestr(filename, "\ufeff" + text)
        paths.append(path)
    return paths


def test_a_window_across_the_change_reads_both_years(tmp_path):
    paths = _year_feeds(tmp_path)
    target = tmp_path / "window.zip"
    counts = importer.write_window_feed(
        list(reversed(paths)), target, date(2026, 12, 10), date(2026, 12, 16)
    )
    assert counts["first"] == date(2026, 12, 10)
    assert counts["last"] == date(2026, 12, 16)
    assert counts["version"] == "20261001+20261101"
    with zipfile.ZipFile(target) as feed:
        trips = {r["trip_id"]: r for r in importer.rows(feed, "trips.txt")}
        services = importer.service_days(feed, date(2026, 12, 10), date(2026, 12, 16))
        stops = {r["stop_id"]: r["stop_name"] for r in importer.rows(feed, "stops.txt")}
        routes = [r["route_id"] for r in importer.rows(feed, "routes.txt")]
        info = next(importer.rows(feed, "feed_info.txt"))
    # Both years' trips, under their own ids; the calendars kept apart.
    assert "t-morning" in trips and "n-morning" in trips
    assert trips["n-morning"]["service_id"] == "20261101:daily"
    assert max(services["daily"]) == date(2026, 12, 12)
    assert min(services["20261101:daily"]) == date(2026, 12, 13)
    # A shared route id is made unique; a shared stop is one row, the newer name.
    assert "r-s1" in routes and "20261101:r-s1" in routes
    assert trips["n-morning"]["route_id"] == "20261101:r-s1"
    assert stops["ch:1:sloid:2"] == "Beta Neu"
    assert (info["feed_start_date"], info["feed_end_date"]) == ("20261210", "20261216")


def test_a_window_inside_one_year_reads_only_that_feed(tmp_path):
    paths = _year_feeds(tmp_path)
    counts = importer.write_window_feed(paths, tmp_path / "w.zip", TODAY, TODAY + timedelta(days=3))
    assert counts["version"] == "20261001"


def test_the_feeds_of_a_window_are_found_by_year():
    url = "https://x/timetable-{year}-gtfs2020/permalink"
    urls = importer.feed_urls(url, date(2026, 9, 28), date(2027, 2, 2))
    assert urls == [url.format(year=y) for y in (2026, 2027, 2028)]
    assert importer.feed_urls("https://x/fixed.zip", TODAY, None) == ["https://x/fixed.zip"]


TRANSFER_HEADER = "from_stop_id,to_stop_id,from_trip_id,to_trip_id,transfer_type,min_transfer_time"


def _transfers(*lines):
    rows = [line.split(",") for line in lines]
    col = {name: i for i, name in enumerate(TRANSFER_HEADER.split(","))}
    return rows, col


def test_a_shorter_walk_lowers_the_transfer_time():
    rows, col = _transfers(
        # Grindelwald: 10 minutes in the station, 5 to the bus stop.
        "grw,grw,,,2,600",
        "grw,bus,,,2,300",
        # A stop with no time of its own and a one-minute walk.
        "a,b,,,2,60",
        # A walk longer than the transfer time changes nothing.
        "x,x,,,2,120",
        "x,y,,,2,300",
        # A trip-bound transfer is neither a walk nor a transfer time.
        "grw,grw,t1,t2,2,30",
        # A zero walk lowers to the floor, not to nothing.
        "z,w,,,2,0",
    )
    result = importer.walks_set_transfer_times(rows, col)
    own = {r[0]: r[5] for r in result if r[0] == r[1] and not r[2]}
    assert own["grw"] == "300"
    # The bus stop's default of two minutes is shorter than the walk already.
    assert "bus" not in own
    # Both ends of a one-minute walk get one minute.
    assert own["a"] == own["b"] == "60"
    assert own["x"] == "120"
    assert "y" not in own
    assert own["z"] == own["w"] == "60"
    # The trip-bound row is left as it was, and nothing is lost.
    assert ["grw", "grw", "t1", "t2", "2", "30"] in result
    assert len(result) == 7 + 4  # rows for a, b, z, w added


def test_the_window_rewrites_transfers_only_when_asked(tmp_path, monkeypatch):
    source = write_feed(tmp_path)
    with zipfile.ZipFile(source, "a") as feed:
        feed.writestr("transfers.txt", TRANSFER_HEADER + "\nch:1:sloid:1,ch:1:sloid:2,,,2,60\n")
    for walks, expected in ((False, 1), (True, 3)):
        target = tmp_path / f"window-{walks}.zip"
        importer.write_window_feed(source, target, TODAY, TODAY + timedelta(days=2), walks)
        with zipfile.ZipFile(target) as feed:
            assert len(list(importer.rows(feed, "transfers.txt"))) == expected


def test_operators_are_named_as_search_ch_names_them():
    from transport_api.timetable.names import operator_name

    assert operator_name("33", "BLS AG (bls)") == "BLS-bls"
    assert operator_name("11", "Schweizerische Bundesbahnen SBB") == "SBB"
    # By full name when the id is unknown (a trip only real time knows).
    assert operator_name(None, "BLS AG (bls)") == "BLS-bls"
    assert operator_name("999999", "Unbekannte Bahn") == "Unbekannte Bahn"


def test_places_are_named_as_search_ch_names_them():
    from transport_api.timetable import places

    bern = [{"name": "Bern", "adminLevel": 4.0}, {"name": "Bern", "adminLevel": 8.0}]
    address = {"type": "ADDRESS", "street": "Neufeldstrasse", "houseNumber": "101", "areas": bern}
    poi = {"type": "PLACE", "name": "Bundeshaus - Parlamentsgebäude", "areas": bern}
    assert places._name(address) == "Bern, Neufeldstrasse 101"
    assert places._name(poi) == "Bundeshaus - Parlamentsgebäude, Bern"
    assert places.house_number("Bubenbergplatz 4c, Bern") == "4c"
    assert places.house_number("Zürich HB") is None


def test_places_keep_to_the_town_asked_for():
    from transport_api.timetable import places

    luzern = places.Place(
        "Luzern, Bahnhofplatz 5", 47.05, 8.31, "address", "5", ("schweiz", "luzern")
    )
    willisau = places.Place(
        "Willisau, Bahnhofplatz 5", 47.12, 7.99, "address", "5", ("schweiz", "willisau")
    )
    museum = places.Place("Museum, Willisau", 47.12, 7.99, "poi", None, ("willisau",))
    assert places._in_town([willisau, luzern], "Bahnhofplatz 5, Luzern") == [luzern]
    assert places._in_town([willisau], "Twing 365n, Hasliberg") == []
    assert places._in_town([museum], "Museum, Luzern") == [museum]
    assert places._in_town([willisau, luzern], "Bahnhofplatz 5") == [willisau, luzern]
    assert places._in_town([luzern], "Bahnhofplatz 5, 6003 Luzern") == [luzern]
    assert places.house_number("Weberstrasse 9.1, Aarburg") == "9.1"
