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
$app['autoloader']->registerNamespace('Predis', __DIR__.'/../vendor/predis/lib');


// create Transport API
$app['api'] = new Transport\API();


// allow cross-domain requests, enable cache
$app->after(function (Request $request, Response $response) {
    $response->headers->set('Access-Control-Allow-Origin', '*');
    $response->headers->set('Cache-Control', 's-maxage=30');
});


// count API calls
$app['redis'] = new Predis\Client(array('host' => 'tetra.redistogo.com', 'port' => 9464, 'password' => '7cd7bdf5a51d601547da3c96d6bae1a2'));
try {
    $app['redis']->connect();
    $app->after(function (Request $request, Response $response) use ($app) {

        $date = date('Y-m-d');
        $key = "stats:calls:$date";

        $app['redis']->incr($key);
    });
} catch (Predis\Network\ConnectionException $e) {
    // ignore connection error
} catch (Predis\ServerException $e) {
    // ignore connection error
}


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
    $via = $request->get('via') ?: null; // TODO support multiple via
    $date = $request->get('date') ?: null;
    $time = $request->get('time') ?: null;
    $limit = $request->get('limit') ?: 4;
    $transportations = $request->get('transportations') ?: array('all');
    $direct = $request->get('direct');
    $sleeper = $request->get('sleeper');
    $couchette = $request->get('chouchette');
    $bike = $request->get('bike');

    if ($limit > 6) {
        return new Response('Invalid value for Parameter `limit`.', 400);
    }

    // get stations
    $stations = array('from' => array(), 'to' => array(), 'via' => array());
    if ($from && $to) {
        $queryarray = array_filter(array('from' => $from, 'to' => $to, 'via' => $via));
        $query = new LocationQuery($queryarray);
        $stations = $app['api']->findLocations($query);
    }

    // get connections
    $connections = array();
    $from = reset($stations['from']) ?: null;
    $to = reset($stations['to']) ?: null;
    $via = array_key_exists('via', $stations) ? $stations['via'] : array();
    if ($from && $to) {
        $query = new ConnectionQuery($from, $to, $via, $date, $time);
        $query->forwardCount = $limit;
        $query->backwardCount = 0;
        $query->transportations = $transportations;
        $query->direct = $direct;
        $query->sleeper = $sleeper;
        $query->couchette = $couchette;
        $query->bike = $bike;
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
    if ($limit > 420) {
        return new Response('Invalid value for Parameter `limit`.', 400);
    }

    $date = $request->get('date');
    if ($date) {
        $date = new DateTime($date, new DateTimeZone('Europe/Zurich'));
    }

    $transportations = $request->get('transportations') ?: array('all');

    if (!$station) {

        $station = $request->get('station');

        $query = new LocationQuery($station);
        $stations = $app['api']->findLocations($query);
        $station = reset($stations);
    }

    if ($station) {
        $query = new StationBoardQuery($station, $date);
        $query->transporations = $transporations;
        $query->maxJourneys = $limit;
        $stationboard = $app['api']->getStationBoard($query);
    }

    return $app->json(array('stationboard' => $stationboard));
});


// run
$app->run(); 
