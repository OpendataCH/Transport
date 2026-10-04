-- Real time, written by realtime.py every 30 seconds and kept across timetable
-- imports: it refers to trips by their feed identifier, not by an import's
-- integer key. Delays are whole minutes; `day` is the trip's service day.
CREATE SCHEMA IF NOT EXISTS rt;

CREATE TABLE IF NOT EXISTS rt.stop_delay (
    trip_id         text    NOT NULL,
    day             date    NOT NULL,
    seq             integer NOT NULL,
    arrival_delay   integer,
    departure_delay integer,
    PRIMARY KEY (trip_id, day, seq)
);

CREATE TABLE IF NOT EXISTS rt.trip_cancelled (
    trip_id text NOT NULL,
    day     date NOT NULL,
    PRIMARY KEY (trip_id, day)
);

CREATE TABLE IF NOT EXISTS rt.feed (
    fetched_at     timestamptz NOT NULL,
    feed_timestamp timestamptz,
    trips          integer NOT NULL,
    delays         integer NOT NULL
);
