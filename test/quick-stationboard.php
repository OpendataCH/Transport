<?php

use Transport\Entity\Query;
use Transport\Entity\Location\Station;
use Transport\Entity\Location\LocationQuery;
use Transport\Entity\Location\NearbyQuery;
use Transport\Entity\Schedule\ConnectionQuery;
use Transport\Entity\Schedule\StationBoardQuery;

require_once 'bootstrap.php';

// Location
$query = new LocationQuery(array('Zürich HB'));

$api = new Transport\API();
$stations = $api->findLocations($query);

$station = reset($stations) ?: null;

// Connection
$date = new \DateTime('');
$query = new StationBoardQuery($station, $date);
$query->maxJourneys = 3;

$xml = $api->sendQuery($query);

$filename = __DIR__ . '/fixtures/stationboard/hafas_response_' . $date->format('Y-m-d') . '.xml';
file_put_contents($filename, $xml->getContent());

// try to format
$dom = new DOMDocument();
$dom->preserveWhiteSpace = false;
$dom->formatOutput = true;
if ($dom->load($filename)) {
    $dom->save($filename);
}
