# Changelog

## 2016-01-23

- #119 Fix for date after midnight in stationboard passlist

## 2016-01-18

- #75 Fixes for delays around midnight in stationboard
- Added scripts for quick capture of fixtures

## 2015-12-23

- Refactored Silex application
- Added integration tests
- Switched to PSR-4 autoloading

## 2015-12-06

- Moved API documentation to separate webpage
- Added Showcase page
- Upgraded dependencies
- Check for SBB server errors
- Added New Relic support

## 2015-12-01

- #103 Added accessibility parameter to /connections

## 2015-11-30

- #117 Add transportations parameter for /locations with coordinates
- New implementation for Transportations binary logic

## 2015-11-21

- Added errors to statistics
- Switch transport.opendata.ch to cURL HTTP client

## 2015-11-02

- #114 Added realtimeAvailability in Stop response
- #113 Fixed departure prognosis for arrival delay

## 2015-10-04

- #104 Implemented bike parameter

## 2015-02-12

- #81 Fixed inverted coordinates

## 2014-10-26

- #100 Fixed couchette parameter naming
- Fixed journeys in stationboard documentation
- Added station to stationboard documentation

## 2014-08-17

- #101 Added arrivalTimestamp and departureTimestamp to stop

## 2014-07-22

- Use dedicated Access-ID created by SBB for Opendata.ch
- Clarified search parameters for /locations

## 2014-06-15

- Added error handler for JSON error messages
- Added separate stats config, they need to be explicitly enabled with stats.config now
- Added optional rate limiting (requires Redis)

## 2013-10-15

- #75 Fix for incorrect date for delays in stationboard
- #95 Replaced deprecated trustProxyData
- #93 Added support for proxy servers

## 2013-09-05

- Improved stationboard location lookup, only search for stations

## 2013-08-13

- #89 Fixed nearby search for names with apostrophe
- Added default limit 40 for stationboard
- #88 Added category code for journeys

## 2013-07-21

- #81 Fixed inverted coordinates in location search
- Deprecated stop/station, use stop/location which also includes addresses
- #80 Allow connection search by address
- Better error handling

## 2012-07-29

- Added capacity to journey
- Always use integer for capacity
- Replaced ResultLimit with Normalizer\FieldNormalizer
- Removed filtered fields from response

## 2012-07-27

- Added easier delay information
- Moved config/local.php to config.php

## 2012-07-19

- Switched to fahrplan.sbb.ch
- #68 Implemented pagination for connections

## 2012-07-16

- Refactored default config
- Added class Transport\Entity\Schedule\Section

## 2012-07-09

- #74 Added missing toXml method for POI

## 2012-06-20

- Use Silex HTTP cache
- Made Redis, HTTP cache and debugging configurable
- Added connections search example
- Use Composer for dependency management

## 2012-06-10

- #69 Added connection duration, transfers, products and service information
- #72 Added distance to nearby search

## 2012-05-01

- #49 Use iso-8859-1 instead of UTF-8 internally for requests
- #57 Added fields filter
- #61 Fixed fatal error for non-station stops
- #64 Fixed address requests

## 2012-04-02

- Added subcategory to journey
- Added walk and journey to section
