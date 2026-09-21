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
