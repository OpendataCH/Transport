# Changelog

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
