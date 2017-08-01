<?php

use Transport\Entity\Location\LocationQuery;
use Transport\Entity\Location\Station;
use Transport\Entity\Query;
use Transport\Entity\Schedule\ConnectionQuery;
use Transport\Entity\Schedule\StationBoardQuery;

require_once 'bootstrap.php';

function download(Query $query, $file)
{
    $api = new Transport\API();

    $response = $api->sendQuery($query);

    $filename = __DIR__.'/fixtures/'.$file;
    file_put_contents($filename, $response->getContent());
}

date_default_timezone_set('Europe/Zurich');

$date = new \DateTime('2016-12-23T14:38:00');

// Location
$query = new LocationQuery('Be');
download($query, 'locations/searchch_response.json');

// Connection
$from = new Station();
$from->name = 'Zürich';
$to = new Station();
$to->name = 'Baden';
$query = new ConnectionQuery($from, $to, [], $date->format('Y-m-d'), $date->format('H:i'));
download($query, 'connections/searchch_response_'.$date->format('Y-m-d').'.json');

// Station Board
$date = new \DateTime('2016-12-23T14:30:00');
$station = new Station();
$station->name = 'Zürich HB';
$query = new StationBoardQuery($station, $date);
$query->maxJourneys = 40;
download($query, 'stationboard/searchch_response_'.$date->format('Y-m-d').'.json');

// Close to Kehrsiten-Bürgenstock
$nearBy = new LocationQuery('');
$nearBy->lat = '47.002347';
$nearBy->lon = '8.379934';
download($nearBy, 'locations/searchch_response_nearby.json');

// Nyon, rte de l'Etraz
$nearBy = new LocationQuery('');
$nearBy->lat = '46.388653';
$nearBy->lon = '6.238729';
download($nearBy, 'locations/searchch_response_nyon.json');
