#!/bin/sh
# Copy the statistics counters (Redis behind /stats.php) from the old host
# Nine into PROD, key by key: what both have is overwritten with Nine's,
# what only PROD has stays. Run from a machine with ssh access to both
# (OPEN-NINE, OPEN-PRD); repeatable - once to try, once at the DNS switch.
# PROD's state before is kept as /opt/transport/prd-redis-before-nine-*.rdb.
set -e
TS=$(date +%Y%m%d-%H%M%S)
LOCAL=$(mktemp -t nine-stats).rdb
ssh OPEN-NINE "redis-cli --rdb /tmp/transport-stats-nine-$TS.rdb >/dev/null && ls -la /tmp/transport-stats-nine-$TS.rdb" 2>/dev/null
scp -q OPEN-NINE:/tmp/transport-stats-nine-$TS.rdb "$LOCAL"
ssh OPEN-NINE "rm -f /tmp/transport-stats-nine-$TS.rdb" 2>/dev/null
scp -q "$LOCAL" OPEN-PRD:/tmp/transport-stats-nine-$TS.rdb
ssh OPEN-PRD "set -e
cd /opt/transport
# Backup of PROD's counters before the import.
sudo docker compose exec -T redis redis-cli --rdb /data/before-nine-$TS.rdb >/dev/null
sudo docker cp transport-redis-1:/data/before-nine-$TS.rdb /opt/transport/prd-redis-before-nine-$TS.rdb
sudo docker compose exec -T redis rm -f /data/before-nine-$TS.rdb
# Nine's snapshot in a Redis of its own, on the compose network.
mkdir -p /tmp/transport-nine-$TS && mv /tmp/transport-stats-nine-$TS.rdb /tmp/transport-nine-$TS/dump.rdb && chmod -R a+rwX /tmp/transport-nine-$TS
sudo docker run -d --rm --name transport-redis-nine --network transport_transport -v /tmp/transport-nine-$TS:/data redis:8-alpine redis-server --save '' --appendonly no >/dev/null
sleep 4
sudo docker compose exec -T service python - <<'EOF'
import redis
nine = redis.Redis(host='transport-redis-nine', port=6379)
live = redis.Redis(host='redis', port=6379)
nine.ping()
before = live.dbsize()
copied = 0
batch = []
def flush():
    global copied
    if not batch: return
    pipe = nine.pipeline()
    for k in batch: pipe.dump(k); pipe.pttl(k)
    out = pipe.execute()
    lp = live.pipeline()
    for i, k in enumerate(batch):
        data, ttl = out[2*i], out[2*i+1]
        if data is None: continue
        lp.restore(k, ttl if ttl and ttl > 0 else 0, data, replace=True)
    lp.execute(); copied += len(batch); batch.clear()
for key in nine.scan_iter(count=1000):
    batch.append(key)
    if len(batch) >= 500: flush()
flush()
print(f'nine keys {nine.dbsize()}, copied {copied}, prod before {before}, after {live.dbsize()}')
for k in ('stats:calls', 'stats:errors'):
    t = live.type(k).decode()
    print(k, t, live.hlen(k) if t == 'hash' else '')
EOF
sudo docker stop transport-redis-nine >/dev/null
sudo rm -rf /tmp/transport-nine-$TS
ls -la /opt/transport/prd-redis-before-nine-$TS.rdb
"
rm -f "$LOCAL"
