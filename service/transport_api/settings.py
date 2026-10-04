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

# Where the upstream timetable lives - the one address the whole service is
# about. Overridable so that a replay stub can take its place in a test run
# without touching anything else.
UPSTREAM_URL = os.environ.get("UPSTREAM_URL", "https://timetable.search.ch/api/")

# Seconds to wait for search.ch, just inside the 60 the vhost allows.
#
# /v1 sets no timeout at all, and a cross-border query has been measured at
# nine seconds - so a shorter limit here would answer 500 where /v1 answers
# data, which is a difference we would have introduced ourselves. Waiting is
# cheap in this service in a way it is not in the old one: the request is
# awaited, not blocking a process.
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
GTFS_URL = os.environ.get(
    "GTFS_URL",
    "https://data.opentransportdata.swiss/dataset/timetable-2026-gtfs2020/permalink",
)

# Days of service loaded ahead of today. The full feed is a year of 42 million
# stop times; a window keeps the database at a fraction of that, and the feed
# is re-read twice a week anyway. Zero loads everything.
GTFS_DAYS = int(os.environ.get("GTFS_DAYS", "14"))

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

# The router behind /v2/connections (MOTIS, on the same feed), e.g.
# `http://motis:8080`. Unset, /v2/connections asks search.ch as /v1 does.
MOTIS_URL = os.environ.get("MOTIS_URL") or None

# The Swiss OpenStreetMap extract, for the router's walks between stops - a
# bus stop and a station are rarely linked in the timetable itself. Unset, the
# router walks only where the timetable says it may. The ingest loop fetches
# it into GTFS_CACHE/osm/ and renews it after OSM_MAX_AGE_DAYS.
OSM_URL = os.environ.get("OSM_URL") or None
OSM_MAX_AGE_DAYS = int(os.environ.get("OSM_MAX_AGE_DAYS", "30"))
