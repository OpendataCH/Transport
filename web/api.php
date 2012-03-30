<?php

require_once __DIR__.'/../silex.phar'; 

use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;

use Transport\Entity\Location\Station;
use Transport\Entity\Location\LocationQuery;
use Transport\Entity\Location\NearbyQuery;
use Transport\Entity\Schedule\ConnectionQuery;
use Transport\Entity\Schedule\StationBoardQuery;

date_default_timezone_set('Europe/Zurich');

// init
$app = new Silex\Application();
$app['debug'] = true;


// autoload
$app['autoloader']->registerNamespace('Transport', __DIR__.'/../lib');
$app['autoloader']->registerNamespace('Buzz', __DIR__.'/../vendor/buzz/lib');


// create Transport API
$app['api'] = new Transport\API();


// allow cross-domain requests, enable cache
$app->after(function (Request $request, Response $response) {
    $response->headers->set('Access-Control-Allow-Origin', '*');
    $response->headers->set('Cache-Control', 's-maxage=30');
});


// index
$app->get('/', function(Request $request) use ($app) {
    return file_get_contents('index.html');
});


// home
$app->get('/v1/', function(Request $request) use ($app) {

    return $app->json(array(
        'date' => date('c'),
        'author' => 'Opendata.ch',
        'version' => '1.0',
    ));
});


// locations
$app->get('/v1/locations', function(Request $request) use ($app) {

    $stations = array();

    $x = $request->get('x') ?: null;
    $y = $request->get('y') ?: null;
    if ($x && $y) {
        $query = new NearbyQuery($x, $y);
        $stations = $app['api']->findNearbyLocations($query);
    }

    $query = $request->get('query');
    if ($query) {
        $query = new LocationQuery($query, $request->get('type'));
        $stations = $app['api']->findLocations($query);
    }

    return $app->json(array('stations' => $stations));
});


// connections
$app->get('/v1/connections', function(Request $request) use ($app) {

    // validate
    $from = $request->get('from');
    $to = $request->get('to');
    $date = $request->get('date') ?: null;
    $time = $request->get('time') ?: null;

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
        $query = new ConnectionQuery($from, $to, $date, $time);
        $connections = $app['api']->findConnections($query);
    }

    return $app->json(array('connections' => $connections, 'from' => $from, 'to' => $to, 'stations' => $stations));
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

    return $app->json(array('stationboard' => $stationboard));
});


// run
$app->run(); 
