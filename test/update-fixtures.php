<?php

use Transport\Entity\Query;
use Transport\Entity\Location\Station;
use Transport\Entity\Location\LocationQuery;
use Transport\Entity\Location\NearbyQuery;
use Transport\Entity\Schedule\ConnectionQuery;
use Transport\Entity\Schedule\StationBoardQuery;

require_once 'bootstrap.php';

function download(Query $query, $file) {

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

function downloadJson($url, $file) {

    $browser = new Buzz\Browser();

    // send request
    $response = $browser->get($url);

    // fix broken JSON
    $content = $response->getContent();
    $content = preg_replace('/(\w+) ?:/i', '"\1":', $content);

    $filename = __DIR__ . '/fixtures/' . $file;
    file_put_contents($filename, $content);

    if (function_exists('exec')) {
        $formatedFilename = $filename . '.formated';
        exec('python -mjson.tool ' . escapeshellarg($filename) . ' 2>/dev/null > ' . escapeshellarg($formatedFilename));

        if (!file_exists($formatedFilename)) {
            return;
        }
        if (filesize($formatedFilename) !== 0) {
            unlink($filename);
            rename($formatedFilename, $filename);
        } else {
            // Do cleanup on failure
            unlink($formatedFilename);
        }
    }
}

// Location
$query = new LocationQuery(array('from' => 'Zürich', 'to' => 'Bern'));
download($query, 'location.xml');

// Connection
$from = new Station('008503000');
$to = new Station('008503504');
$query = new ConnectionQuery($from, $to, array(), '2012-02-13T23:55:00+01:00');
download($query, 'connection.xml');

// Station Board
$station = new Station('008591052'); // Zürich, Bäckeranlage
$query = new StationBoardQuery($station, \DateTime::createFromFormat(\DateTime::ISO8601, '2012-02-13T23:55:00+01:00', new \DateTimeZone('Europe/Zurich')));
$query->maxJourneys = 3;
download($query, 'stationboard.xml');

// Close to Kehrsiten-Bürgenstock
$nearBy = new NearbyQuery('47.002347', '8.379934', 2);
$url = Transport\API::URL_QUERY . '?' . http_build_query($nearBy->toArray());
downloadJson($url, 'location.json');
