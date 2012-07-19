<?php

require_once 'phar://'.__DIR__.'/../silex.phar'; 
require __DIR__.'/../vendor/autoload.php';

use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;

use Transport\Entity\Location\Station;
use Transport\Entity\Location\LocationQuery;
use Transport\Entity\Location\NearbyQuery;
use Transport\Entity\Schedule\ConnectionQuery;
use Transport\Entity\Schedule\MoreConnectionQuery;
use Transport\Entity\Schedule\StationBoardQuery;

use Transport\ResultLimit;

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
$config = __DIR__.'/../config/local.php';
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


// count API calls
if ($app['redis.config']) {
	$app['redis'] = new Predis\Client($app['redis.config']);
	try {
	    $app['redis']->connect();
	    $app->after(function (Request $request, Response $response) use ($app) {

	        $date = date('Y-m-d');
	        $key = "stats:calls:$date";

	        $app['redis']->incr($key);
	    });
	} catch (Exception $e) {
	    // ignore connection error
	    $app['monolog']->addError($e->getMessage());
	}
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
    $result = array('connections' => $connections['connections'], 'reference' => $connections['reference']);
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

//more connections
$app->get('/v1/moreConnections', function(Request $request) use ($app) {
    ResultLimit::setFields($request->get('fields') ?: array());
    $reference = $request->get('reference');
    $forwardCount = $request->get('forwardCount');
    $backwardCount = $request->get('backwardCount');
    if ($forwardCount && $backwardCount) {
        return new Response('Only set one of forwardCount and backwardCount', 400);
    }
    if ($forwardCount > 6 || $backwardCount > 6) {
        return new Response('forwardCount and backwardCount shall not be > 6', 400);
    }
    if ($forwardCount != null) {
        $count = $forwardCount;
        $direction = 'F'; 
    }
    if ($backwardCount != null) {
        $count = $backwardCount;
        $direction = 'B'; 
    }
    $query = new MoreConnectionQuery($reference,$count,$direction);
    $connections = $app['api']->findConnections($query, 'connections');
    $result = array('connections' => $connections['connections'], 'reference' => $connections['reference']);
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
