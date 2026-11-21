-- Run once the rows are in: indexes, the station table, statistics.

ALTER TABLE gtfs_next.stop_times ADD PRIMARY KEY (trip, seq);
CREATE INDEX ON gtfs_next.stop_times (stop, dep_s);
CREATE INDEX ON gtfs_next.stop_times (stop, arr_s);
CREATE INDEX ON gtfs_next.service_dates (service, day);
CREATE UNIQUE INDEX ON gtfs_next.trips (trip_id);
-- /trip?number=: train numbers without the leading zeros /v1 writes.
CREATE INDEX ON gtfs_next.trips (ltrim(short_name, '0'));
CREATE INDEX ON gtfs_next.stops (station);

-- What /v2/locations searches: one row per station. `departures` ranks the
-- busy Bern above a quiet stop of the same name: calls per day over the
-- window, each trip weighted by the days it runs - a trip that runs daily is
-- one row in stop_times, a bus with many calendar variants many rows, and
-- counting rows ranked Geneva buses above the Zürich tram. `mode` is the
-- icon, the most prominent means of transport that calls there.
CREATE TABLE gtfs_next.station AS
WITH days AS (
    SELECT service, count(*) AS n FROM gtfs_next.service_dates GROUP BY service
),
window_days AS (
    SELECT greatest(count(DISTINCT day), 1) AS n FROM gtfs_next.service_dates
),
calls AS (
    SELECT s.station, t.mode, count(*) * max(d.n) AS n
    FROM gtfs_next.stop_times st
    JOIN gtfs_next.stops s ON s.idx = st.stop
    JOIN gtfs_next.trips t ON t.idx = st.trip
    JOIN days d ON d.service = t.service
    GROUP BY s.station, t.mode, t.service
),
ranked AS (
    SELECT station,
           (sum(n) / (SELECT n FROM window_days))::integer AS departures,
           (array_agg(mode ORDER BY CASE mode
                WHEN 'train' THEN 1 WHEN 'tram' THEN 2 WHEN 'ship' THEN 3
                WHEN 'cableway' THEN 4 WHEN 'bus' THEN 5 ELSE 6 END))[1] AS mode
    FROM calls
    GROUP BY station
)
SELECT p.idx,
       coalesce(p.didok, p.stop_id) AS id,
       p.name,
       p.name_norm,
       p.lat,
       p.lon,
       -- A planar point with the longitude shrunk by cos(46.8°), so that the
       -- index's nearest-neighbour order is the true order across Switzerland.
       point(p.lon * 0.6845, p.lat) AS pos,
       coalesce(r.departures, 0) AS departures,
       r.mode
FROM gtfs_next.stops p
LEFT JOIN ranked r ON r.station = p.idx
WHERE p.station = p.idx;

ALTER TABLE gtfs_next.station ADD PRIMARY KEY (idx);
CREATE INDEX ON gtfs_next.station (id);
CREATE INDEX ON gtfs_next.station USING gin (name_norm gin_trgm_ops);
CREATE INDEX ON gtfs_next.station USING gist (pos);

ANALYZE gtfs_next.stop_times;
ANALYZE gtfs_next.trips;
ANALYZE gtfs_next.stops;
ANALYZE gtfs_next.station;
ANALYZE gtfs_next.service_dates;
