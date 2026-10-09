# Deployment

The two servers run the compose files here, each from `/opt/transport` on its
host. Nothing is built there: the images come from this repository's CI
(`registry.gitlab.com/opendata.ch/transport/service:<short SHA>`) and from
MOTIS (`ghcr.io/motis-project/motis`).

| | test | prod |
|---|---|---|
| File | `test/docker-compose.yml` | `prod/docker-compose.yml` |
| Window | 14 days ahead, moved daily | 90 days ahead, moved weekly |
| Router | timetable only | with the Swiss OpenStreetMap extract, map tiles, place search and shared mobility (GBFS) |

## Set up a host

1. Copy the compose file to `/opt/transport/docker-compose.yml`, and next to it
   `docker/motis-run.sh` and (prod) `docker/access_log_receiver.py`.
2. Copy `env.example` to `/opt/transport/.env` and fill it in. It is the only
   place secrets live.
3. Prod only: copy `prod/transport.slice` to `/etc/systemd/system/` and run
   `systemctl daemon-reload`. Every container sits below it
   (`cgroup_parent`), so the stack shares one memory cap of 7 GB without swap
   and yields CPU and disk to the portal. Without the file systemd still
   creates the slice, but with no limits at all.
4. `docker compose up -d`. The ingest container downloads the timetable
   feeds and imports them; MOTIS waits for the first window and builds from it.

## Deploy a build

Set `SERVICE_IMAGE_TAG` in `.env` to the commit's short SHA and run
`docker compose up -d service ingest`. To roll back, put the old tag back.

## Change the router's configuration

`motis-run.sh` writes MOTIS's configuration from environment variables and
rebuilds when they change. A change that takes long to import (map tiles,
GBFS) can be built beside the running router, without an outage:

```sh
docker compose run -d --name transport-motis-build --no-deps \
  -e MOTIS_TILES=1 --entrypoint sh motis /motis-run.sh build
# when it has finished: set the same variables in the compose file, then
docker compose up -d motis   # takes the prebuilt data over in seconds
```

Replace `motis-run.sh` on a host with a new file (`install … new && mv`), never
by writing into the running script.
