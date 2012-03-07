<?php

use Transport\Entity\Location\Station;
use Transport\Entity\Location\LocationQuery;
use Transport\Entity\Schedule\ConnectionQuery;
use Transport\Entity\Schedule\StationBoardQuery;

require_once 'bootstrap.php';

function download($query, $file) {

    $api = new Transport\API();

    $xml = $api->sendQuery($query);

    $filename = __DIR__ . '/fixtures/' . $file;
    file_put_contents($filename, $xml->getContent());

    // try to format
    $dom = new DOMDocument();
    if ($dom->load($filename)) {
        $dom->formatOutput = true;
        $dom->save($filename);
    }
}

// Location
$query = new LocationQuery(array('from' => 'Zürich', 'to' => 'Bern'));
download($query, 'location.xml');

// Connection
$from = new Station('008503000');
$to = new Station('008503504');
$query = new ConnectionQuery($from, $to, '2012-01-31T19:10:00+01:00');
download($query, 'connection.xml');

// Station Board
$station = new Station('008591052'); // Zürich, Bäckeranlage
$query = new StationBoardQuery($station, '2012-02-13T19:10:00+01:00');
$query->maxJourneys = 1;
download($query, 'stationboard.xml');

