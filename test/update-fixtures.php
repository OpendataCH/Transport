<?php

use Transport\Entity\Location\LocationQuery;
use Transport\Entity\Location\NearbyQuery;
use Transport\Entity\Location\Station;
use Transport\Entity\Query;
use Transport\Entity\Schedule\ConnectionQuery;
use Transport\Entity\Schedule\StationBoardQuery;

require_once 'bootstrap.php';

function download(Query $query, $file)
{
    $api = new Transport\API();

    $xml = $api->sendQuery($query);

    $filename = __DIR__.'/fixtures/'.$file;
    file_put_contents($filename, $xml->getContent());

    // try to format
    $dom = new DOMDocument();
    $dom->preserveWhiteSpace = false;
    $dom->formatOutput = true;
    if ($dom->load($filename)) {
        $dom->save($filename);
    }
}

function downloadJson($url, $file)
{
    $browser = new Buzz\Browser();

    // send request
    $response = $browser->get($url);

    $content = $response->getContent();

    $filename = __DIR__.'/fixtures/'.$file;
    file_put_contents($filename, $content);
}

date_default_timezone_set('Europe/Zurich');

$date = new \DateTime('2016-12-23T14:30:00');

// Location
$query = new LocationQuery(['from' => 'Züri', 'to' => 'Bern']);
download($query, 'connections/hafas_response_location.xml');
$query = new LocationQuery('Be');
download($query, 'locations/hafas_response.xml');

// Connection
$from = new Station('008503000');
$to = new Station('008503504');
$query = new ConnectionQuery($from, $to, [], $date->format('Y-m-d'), $date->format('H:i'));
download($query, 'connections/hafas_response_'.$date->format('Y-m-d').'.xml');

// Station Board
$query = new LocationQuery('008591052');
download($query, 'stationboard/hafas_response_location.xml');
$station = new Station('008503000'); // Zürich
$query = new StationBoardQuery($station, $date);
$query->maxJourneys = 3;
download($query, 'stationboard/hafas_response_'.$date->format('Y-m-d').'.xml');

// Close to Kehrsiten-Bürgenstock
$nearBy = new NearbyQuery('47.002347', '8.379934', 2);
$url = Transport\API::URL_QUERY.'?'.http_build_query($nearBy->toArray());
downloadJson($url, 'locations/hafas_response_nearby.json');

// Nyon, rte de l'Etraz
$nearBy = new NearbyQuery('46.388653', '6.238729', 1);
$url = Transport\API::URL_QUERY.'?'.http_build_query($nearBy->toArray());
downloadJson($url, 'locations/hafas_response_nyon.json');
