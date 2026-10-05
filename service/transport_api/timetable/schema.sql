-- The timetable, loaded into a fresh schema and swapped in whole (importer.py).
-- Every key is an integer assigned at import time: the feed's own identifiers
-- are long strings, and stop_times alone has tens of millions of rows.
-- The text identifiers are kept once, on the row they name.

CREATE EXTENSION IF NOT EXISTS pg_trgm;

DROP SCHEMA IF EXISTS gtfs_next CASCADE;
CREATE SCHEMA gtfs_next;

CREATE TABLE gtfs_next.feed_info (
    feed_file   text NOT NULL,
    version     text,
    window_from date NOT NULL,
    window_to   date NOT NULL,
    imported_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE gtfs_next.agency (
    idx  integer PRIMARY KEY,
    name text NOT NULL
);

CREATE TABLE gtfs_next.routes (
    idx        integer PRIMARY KEY,
    agency     integer,
    short_name text,
    category   text,  -- route_desc: S, IC, B, T ...
    route_type integer NOT NULL,
    mode       text   -- train, tram, bus, ship, cableway; null for anything else
);

-- One row per stop or platform. `station` is the idx of the parent, or the
-- row's own idx for a stop without one; `didok` is the number search.ch
-- answers with as the stop id.
CREATE TABLE gtfs_next.stops (
    idx      integer PRIMARY KEY,
    stop_id  text NOT NULL,
    name     text NOT NULL,
    name_norm text NOT NULL,
    lat      double precision,
    lon      double precision,
    station  integer NOT NULL,
    platform text,
    didok    text
);

CREATE TABLE gtfs_next.trips (
    idx        integer PRIMARY KEY,
    trip_id    text NOT NULL,
    route      integer NOT NULL,
    service    integer NOT NULL,
    headsign   text,
    short_name text,
    mode       text,
    first_seq  integer NOT NULL,
    last_seq   integer NOT NULL,
    last_stop  integer NOT NULL
);

-- Seconds from the start of the service day ("noon minus twelve hours"), so
-- 25:10:00 stays 90600 and the trip stays on the day it belongs to.
CREATE TABLE gtfs_next.stop_times (
    trip    integer  NOT NULL,
    seq     integer  NOT NULL,
    stop    integer  NOT NULL,
    arr_s   integer  NOT NULL,
    dep_s   integer  NOT NULL,
    pickup  smallint NOT NULL,
    dropoff smallint NOT NULL
);

-- calendar and calendar_dates multiplied out over the loaded window.
CREATE TABLE gtfs_next.service_dates (
    service integer NOT NULL,
    day     date    NOT NULL
);
