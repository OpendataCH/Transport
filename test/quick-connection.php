<?php

use Transport\Entity\Location\Station;
use Transport\Entity\Schedule\ConnectionQuery;

require_once 'bootstrap.php';

$api = new Transport\API();

$from = new Station();
$from->name = 'Zürich HB';
$to = new Station();
$to->name = 'Olten';

// Connection
$date = new \DateTime('');
$query = new ConnectionQuery($from, $to, [], $date->format('Y-m-d'), $date->format('H:i'));

$response = $api->sendQuery($query);

$filename = __DIR__.'/fixtures/connections/searchch_response_'.$date->format('Y-m-d').'.json';
file_put_contents($filename, $response->getContent());
