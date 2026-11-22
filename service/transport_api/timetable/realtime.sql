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

-- Stops a running trip passes without calling (GTFS-RT SKIPPED).
CREATE TABLE IF NOT EXISTS rt.stop_skipped (
    trip_id text    NOT NULL,
    day     date    NOT NULL,
    seq     integer NOT NULL,
    PRIMARY KEY (trip_id, day, seq)
);

CREATE TABLE IF NOT EXISTS rt.feed (
    fetched_at     timestamptz NOT NULL,
    feed_timestamp timestamptz,
    trips          integer NOT NULL,
    delays         integer NOT NULL
);

-- What was fetched from the sources, when, and how large it was: for the
-- statistics page. Written by the ingest loop and the importer; real time
-- adds a row every 30 seconds, so rows older than 30 days are dropped.
CREATE TABLE IF NOT EXISTS rt.fetch_log (
    at      timestamptz NOT NULL DEFAULT now(),
    source  text        NOT NULL,
    name    text,
    bytes   bigint,
    items   bigint,
    seconds real,
    detail  jsonb
);
CREATE INDEX IF NOT EXISTS fetch_log_source_at ON rt.fetch_log (source, at);

-- The occupancy forecast (occupancy.py), replaced once a day: per train -
-- operator, number and operating day as in the timetable - and station it
-- leaves, 1 (many seats), 2 (few) or 3 (standing room) in each class.
CREATE TABLE IF NOT EXISTS rt.occupancy (
    day      date     NOT NULL,
    operator text     NOT NULL,
    train    text     NOT NULL,
    station  integer  NOT NULL,
    first    smallint,
    second   smallint,
    PRIMARY KEY (day, operator, train, station)
);

-- Train formations (formation_fetch.py): the last answer per train and service
-- day, and a note when somebody asked for one ahead of its time.
CREATE TABLE IF NOT EXISTS rt.formation (
    day        date    NOT NULL,
    operator   text    NOT NULL,
    number     text    NOT NULL,
    asked_at   timestamptz,
    updated_at timestamptz,
    wanted     boolean NOT NULL DEFAULT false,
    stops      jsonb,
    PRIMARY KEY (day, operator, number)
);

-- One row per request to the formation service: the quota is counted from
-- it, and `changed` says whether asking again found anything new. Kept for
-- eight days.
CREATE TABLE IF NOT EXISTS rt.formation_call (
    id       bigserial PRIMARY KEY,
    at       timestamptz NOT NULL,
    day      date NOT NULL,
    operator text NOT NULL,
    number   text NOT NULL,
    reason   text NOT NULL,
    status   integer,
    changed  boolean
);
CREATE INDEX IF NOT EXISTS formation_call_at ON rt.formation_call (at);
