# Deployment

The servers run the compose files here, each from `/opt/transport` on its
host. Nothing is built there: the images come from this repository's CI
(`registry.gitlab.com/opendata.ch/transport/service:<short SHA>`) and from
MOTIS (`ghcr.io/motis-project/motis`).

| | test | prod: entry | prod: API |
|---|---|---|---|
| Host | OPEN-TST | OPEN-PRD | second host (OPARL) |
| File | `test/docker-compose.yml` | `prod/docker-compose.yml` | `oparl/docker-compose.yml` |
| Runs | the whole stack | DNS, nginx vhost, access log, `edge` tunnel | service, db, ingest, motis, redis |
| Window | 14 days ahead, moved daily | | 90 days ahead, moved weekly |
| Router | timetable only | | with the Swiss OpenStreetMap extract, map tiles, place search and shared mobility (GBFS) |

Since 11.10.2026 production is split: on OPEN-PRD the stack took the portal
down twice in one day, so everything that computes moved to the second host.
OPEN-PRD keeps what callers see - the name, plain http without a redirect, the
connection cap and the access log - and `edge` forwards the vhost's upstream
`172.18.0.1:8086` over ssh to the service on `127.0.0.1:18086` there.

## Set up a host

1. Copy the compose file to `/opt/transport/docker-compose.yml`, and next to it
   `docker/motis-run.sh` and (prod) `docker/access_log_receiver.py`.
2. Copy `env.example` to `/opt/transport/.env` and fill it in. It is the only
   place secrets live.
3. Prod entry (OPEN-PRD) only: copy `prod/transport.slice` to
   `/etc/systemd/system/` and run `systemctl daemon-reload`; `edge` and
   `access-log` sit below it. Put the tunnel's key and the second host's
   pinned host key into `/opt/transport/motis-link/` (root, 600) and set
   `MOTIS_SSH_DEST` in `.env`. On the second host the key's line in
   `authorized_keys` must allow nothing but forwarding the service's port:
   `restrict,port-forwarding,permitopen="127.0.0.1:18086",command="/bin/false"`.
4. `docker compose up -d`. The ingest container downloads the timetable
   feeds and imports them; MOTIS waits for the first window and builds from it.

## Deploy a build

On test, and for production **on the second host** (not OPEN-PRD): set
`SERVICE_IMAGE_TAG` in `/opt/transport/.env` to the commit's short SHA and run
`docker compose up -d service ingest`. To roll back, put the old tag back.
Then press `smoke:production` in the pipeline.

OPEN-PRD needs a deploy only when `access_log_receiver.py` or the `edge`
tunnel changes; a new service build never touches it.

## Change the router's configuration

`motis-run.sh` writes MOTIS's configuration from environment variables and
rebuilds when they change. A change that takes long to import (map tiles,
GBFS, the lines along the tracks of `MOTIS_SHAPES`) can be built beside the running router, without an outage:

```sh
docker compose run -d --name transport-motis-build --no-deps \
  -e MOTIS_TILES=1 --entrypoint sh motis /motis-run.sh build
# when it has finished: set the same variables in the compose file, then
docker compose up -d motis   # takes the prebuilt data over in seconds
```

Replace `motis-run.sh` on a host with a new file (`install … new && mv`), never
by writing into the running script.

## Update MOTIS

The MOTIS version is part of what the router is built from, so a new image
always rebuilds instead of reading an import the old release wrote. On the
second host build it beside the running router: put the new image into the
compose file, then run the `motis-run.sh build` container shown above (without
the `-e`) and `docker compose up -d motis` once it has exited. The 2.11.4 build
took 2 minutes there (07.11.2026); test, timetable only, imports in about 40 s
and can simply be restarted.
