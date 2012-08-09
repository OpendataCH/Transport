<?php

require_once 'phar://'.__DIR__.'/../silex.phar'; 
require __DIR__.'/../vendor/autoload.php';

use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;
use Symfony\Component\Serializer\Serializer;
use Symfony\Component\Serializer\Encoder\JsonEncoder;

use Transport\Entity\Location\Station;
use Transport\Entity\Location\LocationQuery;
use Transport\Entity\Location\NearbyQuery;
use Transport\Entity\Schedule\ConnectionQuery;
use Transport\Entity\Schedule\StationBoardQuery;
use Transport\Normalizer\FieldsNormalizer;

date_default_timezone_set('Europe/Zurich');

// init
$app = new Silex\Application();

// default config
$app['debug'] = true;
$app['http_cache'] = false;
$app['buzz.client'] = null;
$app['monolog.level'] = Monolog\Logger::ERROR;
$app['xhprof'] = false;
$app['redis.config'] = false; // array('host' => 'localhost', 'port' => 6379);
$app['proxy'] = false;

/// load config
$config = __DIR__.'/../config.php';
if (stream_resolve_include_path($config)) {
	include $config;
}

// HTTP cache
if ($app['http_cache']) {
	$app->register(new Silex\Provider\HttpCacheServiceProvider(), array(
	    'http_cache.cache_dir' => __DIR__.'/../var/cache/',
	    'http_cache.options' => array('debug' => $app['debug']),
	));
}

// Monolog
$app->register(new Silex\Provider\MonologServiceProvider(), array(
    'monolog.logfile' => __DIR__.'/../var/logs/transport.log',
    'monolog.level' => $app['monolog.level'],
    'monolog.name' => 'transport',
));
$app->before(function (Request $request) use ($app) {
    $app['monolog']->addInfo('- ' . $request->getClientIp() . ' ' . $request->headers->get('referer') . ' ' . $request->server->get('HTTP_USER_AGENT'));
});

// XHProf
if ($app['xhprof']) {
    xhprof_enable();
}

// if hosted behind a reverse proxy
if ($app['proxy']) {
    Request::trustProxyData();
}

// create Transport API
$app['api'] = new Transport\API(new Buzz\Browser($app['buzz.client']));

// allow cross-domain requests, enable cache
$app->after(function (Request $request, Response $response) {
    $response->headers->set('Access-Control-Allow-Origin', '*');
    $response->headers->set('Cache-Control', 's-maxage=30, public');
});

// Serializer
$app['serializer'] = $app->share(function () use ($app) {
    $fields = $app['request']->get('fields') ?: array();
    return new Serializer(array(new FieldsNormalizer($fields)), array('json' => new JsonEncoder()));
});


// statistics
$redis = null;
try {
    if ($app['redis.config']) {
        $redis = new Predis\Client($app['redis.config']);
        $redis->connect();
    }
} catch (Exception $e) {
    $app['monolog']->addError($e->getMessage());
    $redis = null;
}
$app['stats'] = new Transport\Statistics($redis);
$app->after(function (Request $request, Response $response) use ($app) {
    $app['stats']->call();
    $app['stats']->resource($request->getPathInfo());
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

    $result = array('stations' => $stations);

    $json = $app['serializer']->serialize((object) $result, 'json');
    return new Response($json, 200, array('Content-Type' => 'application/json'));
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
    $limit = $request->get('limit') ?: null;
    $page = $request->get('page') ?: null;
    $transportations = $request->get('transportations');
    $direct = $request->get('direct');
    $sleeper = $request->get('sleeper');
    $couchette = $request->get('chouchette');
    $bike = $request->get('bike');

    if ($limit > 6) {
        return new Response('Maximal value of argument `limit` is 6.', 400);
    }
    if ($page > 10) {
        return new Response('Maximal value of argument `page` is 10.', 400);
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
        $app['stats']->station($from);
        $app['stats']->station($to);

        $query = new ConnectionQuery($from, $to, $via, $date, $time);
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
        if ($limit) {
            $query->limit = $limit;
        }
        if ($page) {
            $query->page = $page;
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
        $connections = $app['api']->findConnections($query);
    }

    $result = array(
        'connections' => $connections,
        'from' => $from,
        'to' => $to,
        'stations' => $stations,
    );

    $json = $app['serializer']->serialize((object) $result, 'json');
    return new Response($json, 200, array('Content-Type' => 'application/json'));
});


// station board
$app->get('/v1/stationboard', function(Request $request) use ($app) {

    $stationboard = array();

    $limit = $request->get('limit');
    if ($limit > 420) {
        return new Response('Invalid value for Parameter `limit`.', 400);
    }

    $date = $request->get('date');
    if ($date) {
        $date = new DateTime($date, new DateTimeZone('Europe/Zurich'));
    }

    $transportations = $request->get('transportations');

    $station = $request->get('station') ?: $request->get('id');

    $query = new LocationQuery($station);
    $stations = $app['api']->findLocations($query);
    $station = reset($stations);

    if ($station) {
        $app['stats']->station($station);

        $query = new StationBoardQuery($station, $date);
        if ($transportations) {
            $query->transportations = $transportations;
        }
        $query->maxJourneys = $limit;
        $stationboard = $app['api']->getStationBoard($query);
    }

    $result = array('stationboard' => $stationboard);

    $json = $app['serializer']->serialize((object) $result, 'json');
    return new Response($json, 200, array('Content-Type' => 'application/json'));
});


// run
if ($app['http_cache']) {
    $app['http_cache']->run();
} else {
	$app->run();
}

// save XHProf run
if ($app['xhprof']) {

    $data = xhprof_disable();

    include_once __DIR__.'/../vendor/facebook/xhprof/xhprof_lib/utils/xhprof_lib.php';
    include_once __DIR__.'/../vendor/facebook/xhprof/xhprof_lib/utils/xhprof_runs.php';

    $xhprof = new XHProfRuns_Default(__DIR__.'/../var/xhprof');
    $run_id = $xhprof->save_run($data, 'transport');
}
