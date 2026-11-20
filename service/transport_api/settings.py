"""Runtime settings, all of them optional.

The service has no configuration file. What little it needs comes from the
environment, so the same image runs in every environment and a deployment is a
tag plus a handful of variables.
"""

import os

# Europe/Zurich, always - a constant and not a setting. The PHP application
# sets the zone explicitly at boot and the /v1 shape prints local times without
# an offset, so a service running on UTC would answer an hour or two beside the
# truth without failing anything. Leaving that to the environment would make
# the single most invisible regression in the whole exercise a matter of a
# stray variable. The image sets TZ as well, for everything below Python.
TIMEZONE = "Europe/Zurich"

# What the running image is. CI stamps the short commit SHA into the image at
# build time; a working copy says "dev".
VERSION = os.environ.get("SERVICE_VERSION", "dev")

# Seconds to wait for the router, just inside the 60 the vhost allows.
# (The name is from when the upstream was search.ch.)
UPSTREAM_TIMEOUT = float(os.environ.get("UPSTREAM_TIMEOUT", "55"))

# The Redis that /stats.php reads, e.g. `redis://redis:6379/0` - the same one
# the PHP application writes to, so that one history runs across both. Unset,
# nothing is counted; that is what a test run and a working copy want.
REDIS_URL = os.environ.get("REDIS_URL") or None

# Seconds a statistics write may take before it is given up. Counting is never
# worth holding an answer for.
REDIS_TIMEOUT = float(os.environ.get("REDIS_TIMEOUT", "0.25"))

# The timetable database behind /v2/locations and /v2/stationboard, e.g.
# `postgresql://transport:transport@db:5432/transport`. Unset, those two routes
# answer 503 and everything else works as before.
DATABASE_URL = os.environ.get("DATABASE_URL") or None

# The national GTFS feed. The permalink redirects to the newest file and needs
# no key; the CKAN API next to it does.
#
# One feed per timetable year, which changes in mid-December; `{year}` stands
# for it, so that next year's feed is found once it is published and a window
# across the change reads both.
GTFS_URL = os.environ.get(
    "GTFS_URL",
    "https://data.opentransportdata.swiss/dataset/timetable-{year}-gtfs2020/permalink",
)

# Days of service loaded ahead of today. The full feed is a year of 42 million
# stop times; a window keeps the database at a fraction of that, and the feed
# is re-read twice a week anyway. Zero loads everything.
GTFS_DAYS = int(os.environ.get("GTFS_DAYS", "14"))

# How far the window falls behind before it is moved on. One re-imports
# daily; more saves imports (and the router's rebuild) at the price of up to
# that many more days back.
GTFS_WINDOW_STEP_DAYS = max(int(os.environ.get("GTFS_WINDOW_STEP_DAYS", "1")), 1)

# Days of service loaded before today. One keeps the trips of yesterday's
# service day that run past midnight; more answers questions about the recent
# past, at the cost of a few more trips per day kept.
GTFS_PAST_DAYS = max(int(os.environ.get("GTFS_PAST_DAYS", "1")), 1)

# Where a downloaded feed is kept between runs, so that an unchanged file is
# not fetched again.
GTFS_CACHE = os.environ.get("GTFS_CACHE", "/tmp/gtfs")

# The real-time feed and its key from api-manager.opentransportdata.swiss.
# Without a key the ingest loop loads the timetable and skips real time.
GTFS_RT_URL = os.environ.get("GTFS_RT_URL", "https://api.opentransportdata.swiss/la/gtfs-rt")
OTD_API_KEY = os.environ.get("OTD_API_KEY") or None

# The railways' occupancy forecast (timetable/occupancy.py): free, no key, one
# ZIP a day. Empty switches it off. Days of it kept ahead, today included.
OCCUPANCY_URL = os.environ.get(
    "OCCUPANCY_URL",
    "https://data.opentransportdata.swiss/dataset/occupancy-forecast-json-dataset/permalink",
)
OCCUPANCY_DAYS = max(int(os.environ.get("OCCUPANCY_DAYS", "7")), 1)

# The router behind /connections (MOTIS, on the same feed), e.g.
# `http://motis:8080`. Unset, /connections answers 503.
MOTIS_URL = os.environ.get("MOTIS_URL") or None

# Whether the router was built with its place search (MOTIS_TILES on the
# router). Without it, an OJP location request for a stop id crashes MOTIS
# 2.11.4 - it reads the missing search unchecked - so /ojp20 refuses it.
MOTIS_GEOCODING = os.environ.get("MOTIS_GEOCODING", "0") not in ("0", "false", "")

# Journey plans one worker asks the router at once, and how long a plan may
# wait for its turn before it is refused with 429 (see timetable/router.py).
MOTIS_CONCURRENCY = int(os.environ.get("MOTIS_CONCURRENCY", "4"))
MOTIS_QUEUE_SECONDS = float(os.environ.get("MOTIS_QUEUE_SECONDS", "3"))

# How long a connection asked "from now" (no date, no time) is answered again
# from the cache. Home Assistant asks the same one every 90 seconds, so a
# little more than that answers every second poll (see response_cache.py).
CONNECTIONS_NOW_CACHE_SECONDS = int(os.environ.get("CONNECTIONS_NOW_CACHE_SECONDS", "100"))

# The Swiss OpenStreetMap extract, for the router's walks between stops - a
# bus stop and a station are rarely linked in the timetable itself. Unset, the
# router walks only where the timetable says it may. The ingest loop fetches
# it into GTFS_CACHE/osm/ and renews it after OSM_MAX_AGE_DAYS.
OSM_URL = os.environ.get("OSM_URL") or None
OSM_MAX_AGE_DAYS = int(os.environ.get("OSM_MAX_AGE_DAYS", "30"))

# The router (MOTIS) times a walk between two stops as the longest of the
# walk and the transfer times of both stops; HAFAS, which the Swiss data is
# written for, lets the walk replace them. On, the router's window lowers a
# stop's transfer time to its shortest walk, so that the walk counts as given
# (Grindelwald: 5 minutes to the bus, not the station's 10). Off, the feed's
# transfers go to the router unchanged.
GTFS_WALK_SETS_TRANSFER = os.environ.get("GTFS_WALK_SETS_TRANSFER", "1") not in ("0", "false", "")

# How long a connection may walk from where it starts to its first vehicle,
# and from its last vehicle to where it ends. The router's own default is
# 15 minutes, which loses connections search.ch finds with a 16-minute walk
# at either end (Yverdon-les-Bains to Philosophes).
MOTIS_MAX_WALK_SECONDS = int(os.environ.get("MOTIS_MAX_WALK_SECONDS", "1200"))

# Walking speed, metres a second, on the way to the first stop and from the
# last. The router walks along the streets to the platform itself, at about
# 1.2 by default: near a large station that came out minutes longer than
# search.ch's walks. 1.4 is about 5 km/h, what journey planners assume.
# Walks between stops are fixed when the router imports and are not changed.
MOTIS_PEDESTRIAN_SPEED = os.environ.get("MOTIS_PEDESTRIAN_SPEED", "1.4")
