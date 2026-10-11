#!/bin/sh
# Runs MOTIS - the router behind /v2/connections - on the timetable the
# database holds, and follows it when it changes.
#
# The ingest container writes the name of the feed it has imported to
# /gtfs/CURRENT (the shared GTFS cache, mounted read-only here). When that
# name changes, the feed is imported into a fresh directory while the server
# keeps answering, and the server is then restarted on it: a few seconds
# without routing, twice a week. The real-time key comes from OTD_API_KEY and
# is written only into the configuration inside /data.
#
# With MOTIS_OSM naming an OpenStreetMap extract (fetched by ingest), the
# router also walks along streets between stops where the timetable has no
# transfer; the extract changing (its size) rebuilds just like a new feed.
#
# Meant as the entrypoint of the official image (ghcr.io/motis-project/motis),
# which ships busybox: `sh /motis-run.sh`.
set -eu

FEEDS=/gtfs
DATA=/data
SERVER=""
FAILED=""

trap 'if [ -n "$SERVER" ]; then kill "$SERVER" 2>/dev/null; wait "$SERVER" 2>/dev/null; fi; exit 0' TERM INT

# The window file already holds only the days the database has; MOTIS just
# has to look far enough back (MOTIS_PAST_DAYS, like GTFS_PAST_DAYS) and ahead
# (MOTIS_DAYS) not to cut it again.
first_day() { date -u -d "@$(( $(date +%s) - ${MOTIS_PAST_DAYS:-1} * 86400 ))" +%Y-%m-%d; }

feed() { cat "$FEEDS/CURRENT" 2>/dev/null | tr -d '[:space:]'; }
osm() { if [ -n "${MOTIS_OSM:-}" ] && [ -s "$MOTIS_OSM" ]; then echo "$MOTIS_OSM"; fi; }
# Raise when the configuration written below changes: a running router
# rebuilds only when what it is built from changes, and this is part of it.
CONFIG_REVISION=3

# What the router should be built from: the window, the street network with
# its size when there is one, and the configuration.
wanted() {
    f=$(feed)
    [ -n "$f" ] || return 0
    o=$(osm)
    # stat, not `wc -c`: busybox wc reads the whole 550 MB extract to count
    # it, and this runs every minute.
    if [ -n "$o" ]; then f="$f+osm$(stat -c %s "$o")"; fi
    if [ -n "$o" ] && [ -n "${MOTIS_TILES:-}" ]; then f="$f+tiles"; fi
    if [ -n "$o" ] && [ -n "${MOTIS_GBFS_URL:-}" ]; then f="$f+gbfs"; fi
    if [ -n "$o" ] && [ -n "${MOTIS_REVERSE_GEOCODING:-}" ]; then f="$f+rgeo"; fi
    echo "$f+r$CONFIG_REVISION"
}
loaded() { cat "$DATA/current/FEED" 2>/dev/null | tr -d '[:space:]'; }

build() {
    target=$(wanted)
    feed=$(feed)
    street=$(osm)
    echo "motis-run: importing $target"
    rm -rf "$DATA/next"
    mkdir -p "$DATA/next"
    {
        echo "server:"
        echo "  port: 8080"
        if [ -n "$street" ]; then
            echo "osm: $street"
            echo "street_routing: true"
            if [ -n "${MOTIS_TILES:-}" ]; then
                # The map behind the router's own page (/routing/) and its
                # place search. Built once per street network.
                echo "tiles:"
                echo "  profile: /tiles-profiles/full.lua"
                echo "geocoding: true"
            fi
            if [ -n "${MOTIS_REVERSE_GEOCODING:-}" ]; then
                # The address nearest a coordinate, first in /locations?x&y.
                echo "reverse_geocoding: true"
            fi
            if [ -n "${MOTIS_GBFS_URL:-}" ]; then
                # Bikes, scooters and cars to rent, for the first and last mile
                # (sharedmobility.ch: one Lamassu manifest over all providers,
                # which asks for an e-mail address in Authorization).
                echo "gbfs:"
                echo "  feeds:"
                echo "    ch:"
                echo "      url: $MOTIS_GBFS_URL"
                if [ -n "${MOTIS_GBFS_AUTHORIZATION:-}" ]; then
                    echo "      headers:"
                    echo "        Authorization: $MOTIS_GBFS_AUTHORIZATION"
                fi
                echo "  update_interval: 60"
            fi
        fi
        echo "timetable:"
        echo "  first_day: $(first_day)"
        echo "  num_days: ${MOTIS_DAYS:-150}"
        # Vehicles on the map (/api/v6/map/trips), for the map example. The
        # Swiss feed has no shapes.txt, so they move in straight lines
        # between stops.
        echo "  railviz: true"
        echo "  with_shapes: false"
        echo "  update_interval: 60"
        # Longer than the default 15: MOTIS leaves out a walk of exactly the
        # limit, and the timetable has 15-minute ones (Trübsee to the chair
        # lift to the Jochpass).
        echo "  max_footpath_length: 20"
        if [ -n "$street" ]; then
            # Keep the timetable's own transfers; add street walks where it has none.
            echo "  extend_missing_footpaths: true"
        fi
        echo "  datasets:"
        echo "    ch:"
        echo "      path: $FEEDS/$feed"
        if [ -n "${OTD_API_KEY:-}" ]; then
            echo "      rt:"
            echo "        - url: https://api.opentransportdata.swiss/la/gtfs-rt"
            echo "          headers:"
            echo "            Authorization: Bearer $OTD_API_KEY"
        fi
    } > "$DATA/config.yml"
    # Explicitly: `set -e` does not hold inside a function called as an `if`
    # condition, and a half-imported directory must never be swapped in.
    /motis import -c "$DATA/config.yml" -d "$DATA/next" || return 1
    echo "$target" > "$DATA/next/FEED"
}

swap() {
    rm -rf "$DATA/previous"
    if [ -d "$DATA/current" ]; then mv "$DATA/current" "$DATA/previous"; fi
    mv "$DATA/next" "$DATA/current"
    rm -rf "$DATA/previous"
}

serve() {
    /motis server -d "$DATA/current" &
    SERVER=$!
}

until [ -n "$(wanted)" ]; do
    echo "motis-run: waiting for the first timetable import"
    sleep 30
done

# `motis-run.sh build`: only build next/ and stop, in a container of its own
# beside the one that routes - for a change that takes long to import (the
# map tiles). The routing container then finds it ready when it restarts.
if [ "${1:-}" = "build" ]; then
    build || exit 1
    echo "motis-run: built $(cat "$DATA/next/FEED"); restart the router to use it"
    exit 0
fi

prebuilt() { cat "$DATA/next/FEED" 2>/dev/null | tr -d '[:space:]'; }

if [ "$(loaded)" != "$(wanted)" ]; then
    if [ "$(prebuilt)" = "$(wanted)" ]; then
        echo "motis-run: using the prebuilt $(prebuilt)"
    else
        build || exit 1
    fi
    swap
fi
serve

while true; do
    sleep 60 &
    wait $!
    if ! kill -0 "$SERVER" 2>/dev/null; then
        echo "motis-run: the server stopped" >&2
        exit 1
    fi
    # A feed that failed to import is not retried every minute; a new one is.
    if [ "$(loaded)" != "$(wanted)" ] && [ "$(wanted)" != "$FAILED" ]; then
        if build; then
            kill "$SERVER"
            wait "$SERVER" || true
            swap
            serve
        else
            FAILED=$(wanted)
            echo "motis-run: import of $FAILED failed; still routing on $(loaded)" >&2
        fi
    fi
done
