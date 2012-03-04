<?php

require_once __DIR__.'/../silex.phar'; 

use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;

use Transport\Entity\Location\Station;
use Transport\Entity\Location\LocationQuery;
use Transport\Entity\Schedule\ConnectionQuery;
use Transport\Entity\Schedule\StationBoardQuery;

// init
$app = new Silex\Application();
$app['debug'] = true;


// autoload
$app['autoloader']->registerNamespace('Transport', __DIR__.'/../lib');
$app['autoloader']->registerNamespace('Buzz', __DIR__.'/../vendor/buzz/lib');


// create Transport API
$app['api'] = new Transport\API();


// allow cross-domain requests
$app->after(function (Request $request, Response $response) {
    $response->headers->set('Access-Control-Allow-Origin', '*');
});


// home
$app->get('/v1/', function(Request $request) use ($app) {

    return json_encode(array(
        'date' => date('c'),
        'author' => 'Liip AG',
        'version' => '1.0',
    ));
});


// locations
$app->get('/v1/locations', function(Request $request) use ($app) {

    $query = new LocationQuery($request->get('query'), $request->get('type'));
    $stations = $app['api']->findLocations($query);

    return json_encode(array('stations' => $stations));
});


// connections
$app->get('/v1/connections', function(Request $request) use ($app) {

   // validate
   $from = $request->get('from');
   $to = $request->get('to');

   // get stations
   $stations = array('from' => array(), 'to' => array());
   if ($from && $to) {
       $query = new LocationQuery(array('from' => $from, 'to' => $to));
       $stations = $app['api']->findLocations($query);
   }

   // get connections
   $connections = array();
   $from = reset($stations['from']) ?: null;
   $to = reset($stations['to']) ?: null;
   if ($from && $to) {

       $query = new ConnectionQuery($from, $to);
       $connections = $app['api']->findConnections($query);
   }

   return json_encode(array('connections' => $connections, 'from' => $from, 'to' => $to, 'stations' => $stations));
});


// station board
$app->get('/v1/stationboard', function(Request $request) use ($app) {

    $station = null;
    $stationboard = array();

    $id = $request->get('id');
    if ($id) {
        $station = new Station($id);
    }

    $limit = $request->get('limit');

    if (!$station) {

        $station = $request->get('station');

        $query = new LocationQuery($station);
        $stations = $app['api']->findLocations($query);
        $station = reset($stations);
    }

    if ($station) {
        $query = new StationBoardQuery($station);
        $query->maxJourneys = $limit;
        $stationboard = $app['api']->getStationBoard($query);
    }

    return json_encode(array('stationboard' => $stationboard));
});


// run
$app->run(); 
