# ruff: noqa: E501 - the header lines of the feed are what they are
"""A GTFS feed small enough to read, with the cases that break naive code.

- a station with a parent and two platforms, and a stop without a parent;
- a trip past midnight (`24:10:00`), which belongs to the day before;
- a trip on a headway (frequencies.txt), which is a template, not a run;
- a service removed on one day and one added on another (calendar_dates);
- the files start with a byte-order mark, as the Swiss ones do.

Monday 5 October 2026 is "today" in the tests; Sunday 25 October is the day
the clocks go back.
"""

import zipfile
from datetime import date
from pathlib import Path

TODAY = date(2026, 10, 5)
CLOCKS_BACK = date(2026, 10, 25)

FILES = {
    "agency.txt": """agency_id,agency_name,agency_url,agency_timezone
"11","Test Bahn","https://example.org","Europe/Zurich"
""",
    "routes.txt": """route_id,agency_id,route_short_name,route_long_name,route_desc,route_type
"r-s1","11","S1","","S","109"
"r-b10","11","10","","B","700"
""",
    "stops.txt": """stop_id,stop_name,stop_lat,stop_lon,location_type,parent_station,platform_code,didok
"ch:1:sloid:1","Alpha","46.9","7.4","1","","","8500001"
"ch:1:sloid:1:1:1","Alpha","46.9001","7.4001","","ch:1:sloid:1","1","8500001"
"ch:1:sloid:1:1:2","Alpha","46.9002","7.4002","","ch:1:sloid:1","2","8500001"
"ch:1:sloid:2","Beta","47.0","7.5","1","","","8500002"
"ch:1:sloid:2:0:1","Beta","47.0001","7.5001","","ch:1:sloid:2","3","8500002"
"8500003","Gamma, Dorf","47.1","7.6","","","","8500003"
""",
    "calendar.txt": """service_id,monday,tuesday,wednesday,thursday,friday,saturday,sunday,start_date,end_date
"daily","1","1","1","1","1","1","1","20260101","20261231"
"sundays","0","0","0","0","0","0","1","20260101","20261231"
""",
    "calendar_dates.txt": """service_id,date,exception_type
"daily","20261006","2"
"extra","20261007","1"
""",
    "trips.txt": """route_id,service_id,trip_id,trip_headsign,trip_short_name
"r-s1","daily","t-morning","Gamma, Dorf","1234"
"r-s1","daily","t-night","Beta","1299"
"r-b10","extra","t-extra","Gamma, Dorf","77"
"r-b10","daily","t-headway","Beta","88"
"r-s1","sundays","t-sunday","Beta","4321"
""",
    "stop_times.txt": """trip_id,arrival_time,departure_time,stop_id,stop_sequence,pickup_type,drop_off_type
"t-morning","08:00:00","08:00:00","ch:1:sloid:1:1:1","1","0","0"
"t-morning","08:10:00","08:12:00","ch:1:sloid:2:0:1","2","0","0"
"t-morning","08:30:00","08:30:00","8500003","3","0","0"
"t-night","24:10:00","24:10:00","ch:1:sloid:1:1:2","1","0","0"
"t-night","25:10:00","25:10:00","ch:1:sloid:2:0:1","2","0","0"
"t-extra","12:00:00","12:00:00","ch:1:sloid:1:1:1","1","0","0"
"t-extra","12:20:00","12:20:00","8500003","2","0","0"
"t-headway","00:00:00","00:00:00","ch:1:sloid:1:1:2","1","0","0"
"t-headway","00:05:00","00:05:00","ch:1:sloid:2:0:1","2","0","0"
"t-sunday","08:00:00","08:00:00","ch:1:sloid:1:1:1","1","0","0"
"t-sunday","08:10:00","08:10:00","ch:1:sloid:2:0:1","2","0","0"
""",
    "frequencies.txt": """trip_id,start_time,end_time,headway_secs,exact_times
"t-headway","09:00:00","09:30:00","600","1"
""",
    "feed_info.txt": """feed_publisher_name,feed_publisher_url,feed_lang,feed_start_date,feed_end_date,feed_version
"Test","https://example.org","DE","20260101","20261231","20261001"
""",
}


def write_feed(directory: Path, name: str = "gtfs_test_20261001.zip") -> Path:
    path = directory / name
    with zipfile.ZipFile(path, "w") as archive:
        for filename, text in FILES.items():
            archive.writestr(filename, "﻿" + text)
    return path
