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

# Where the upstream timetable lives. Not used yet - S1 is the first stage that
# calls it - but named here because it is the one address the whole service is
# about.
UPSTREAM_URL = os.environ.get("UPSTREAM_URL", "https://timetable.search.ch/api/")
