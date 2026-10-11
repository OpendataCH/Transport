#!/bin/sh
# Pushes the timetable window ingest imported (named in CURRENT) and the OSM
# extract to the router on the second host (MOTIS_SSH_DEST, user@host), so
# that it routes on the very feed the database here holds. CURRENT goes last:
# the router rebuilds when it changes, and must find the window complete by
# then. Older windows are removed there once the new one is across. rsync
# skips what is already there, so a minute's check costs one ssh connection.
set -u
apk add -q --no-cache rsync openssh-client >/dev/null || exit 1

SSH="ssh -i /k/id_ed25519 -o UserKnownHostsFile=/k/known_hosts -o StrictHostKeyChecking=yes -o BatchMode=yes -o ConnectTimeout=20"
DEST=${MOTIS_SSH_DEST:?}
DONE=""

while true; do
    feed=$(tr -d '[:space:]' < /g/CURRENT 2>/dev/null)
    osm_size=$(stat -c %s /g/osm/switzerland.osm.pbf 2>/dev/null)
    want="$feed+$osm_size"
    if [ -n "$feed" ] && [ "$want" != "$DONE" ]; then
        echo "gtfs-sync: pushing $want"
        if rsync -rt --delete --delete-excluded -e "$SSH" \
                --filter='P /CURRENT' \
                --include="/$feed" --include='/osm/' --include='/osm/switzerland.osm.pbf' \
                --exclude='*' /g/ "$DEST:/" &&
           rsync -t -e "$SSH" /g/CURRENT "$DEST:/CURRENT"; then
            DONE="$want"
            echo "gtfs-sync: router has $want"
        else
            echo "gtfs-sync: push of $want failed, retrying in a minute" >&2
        fi
    fi
    sleep 60
done
