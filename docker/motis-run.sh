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
# Meant as the entrypoint of the official image (ghcr.io/motis-project/motis),
# which ships busybox: `sh /motis-run.sh`.
set -eu

FEEDS=/gtfs
DATA=/data
SERVER=""
FAILED=""

trap 'if [ -n "$SERVER" ]; then kill "$SERVER" 2>/dev/null; wait "$SERVER" 2>/dev/null; fi; exit 0' TERM INT

wanted() { cat "$FEEDS/CURRENT" 2>/dev/null | tr -d '[:space:]'; }
loaded() { cat "$DATA/current/FEED" 2>/dev/null | tr -d '[:space:]'; }

build() {
    feed=$(wanted)
    echo "motis-run: importing $feed"
    rm -rf "$DATA/next"
    mkdir -p "$DATA/next"
    {
        echo "server:"
        echo "  port: 8080"
        echo "timetable:"
        echo "  first_day: TODAY"
        echo "  num_days: 30"
        echo "  railviz: false"
        echo "  with_shapes: false"
        echo "  update_interval: 60"
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
    echo "$feed" > "$DATA/next/FEED"
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

if [ "$(loaded)" != "$(wanted)" ]; then
    build || exit 1
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
