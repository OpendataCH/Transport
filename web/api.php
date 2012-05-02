<?php

require_once __DIR__.'/../silex.phar'; 

use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;

use Transport\Entity\Location\Station;
use Transport\Entity\Location\LocationQuery;
use Transport\Entity\Location\NearbyQuery;
use Transport\Entity\Schedule\ConnectionQuery;
use Transport\Entity\Schedule\StationBoardQuery;

use Transport\ResultLimit;

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
    if (is_array($request->get('via'))) {
        $via = $request->get('via');
        if (count($via) > 5) {
            return new Response('Invalid via count (max 5 allowed)', 400);
        }
    } else if ($request->get('via')) {
        $via = array($request->get('via'));
    } else {
        $via = array();
    }
    $date = $request->get('date') ?: null;
    $time = $request->get('time') ?: null;
    $isArrivalTime = $request->get('isArrivalTime') ?: null;
    $limit = $request->get('limit') ?: 4;
    $transportations = $request->get('transportations');
    $direct = $request->get('direct');
    $sleeper = $request->get('sleeper');
    $couchette = $request->get('chouchette');
    $bike = $request->get('bike');

    ResultLimit::setFields($request->get('fields') ?: array());

    if ($limit > 6) {
        return new Response('Maximal value of argument `limit` is 6.', 400);
    }

    // get stations
    $stations = array('from' => array(), 'to' => array(), 'via' => array());
    if ($from && $to) {
        $query = new LocationQuery(array('from' => $from, 'to' => $to, 'via' => $via));
        $stations = $app['api']->findLocations($query);
    }
    
    // get connections
    $connections = array();
    $from = reset($stations['from']) ?: null;
    $to = reset($stations['to']) ?: null;
    $via = array();
    foreach ($stations as $k => $v) {
        if (preg_match("/^via[0-9]+$/", $k) && $v) {
            $via[] = reset($v);
        }
    }

    if ($from && $to) {
        $query = new ConnectionQuery($from, $to, $via, $date, $time);
        $query->forwardCount = $limit;
        $query->backwardCount = 0;
        if ($isArrivalTime !== null) {
            switch ($isArrivalTime) {
                case 0:
                case "false":
                    $query->isArrivalTime = false;
                    break;
                case 1:
                case "true":
                    $query->isArrivalTime = true;
                    break;
                default:
                    //wrong parameter value
                    break;
            }
        }
        if ($transportations) {
            $query->transportations = $transportations;
        }
        if ($direct) {
            $query->direct = $direct;
        }
        if ($sleeper) {
            $query->sleeper = $sleeper;
        }
        if ($couchette) {
            $query->couchette = $couchette;
        }
        if ($bike) {
            $query->bike = $bike;
        }
        $connections = $app['api']->findConnections($query, 'connections');
    }
    $result = array('connections' => $connections);
    if (ResultLimit::isFieldSet('from')) {
        $result = array_merge($result,array('from' => $from));   
    }
    if (ResultLimit::isFieldSet('to')) {
        $result = array_merge($result,array('to' => $to));   
    }
    if (ResultLimit::isFieldSet('stations')) {
        $result = array_merge($result,array('stations' => $stations));   
    }
    return $app->json($result);
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

    $transportations = $request->get('transportations');
    
    ResultLimit::setFields($request->get('fields') ?: array());

    if (!$station) {

        $station = $request->get('station');

        $query = new LocationQuery($station);
        $stations = $app['api']->findLocations($query);
        $station = reset($stations);
    }

    if ($station) {
        $query = new StationBoardQuery($station, $date);
        if ($transportations) {
            $query->transportations = $transportations;
        }
        $query->maxJourneys = $limit;
        $stationboard = $app['api']->getStationBoard($query, 'stationboard');
    }
    return $app->json(array('stationboard' => $stationboard));
});


// run
$app->run(); 
