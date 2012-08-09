<?php

require_once 'phar://'.__DIR__.'/../silex.phar'; 
require __DIR__ . '/../vendor/autoload.php';

use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;

date_default_timezone_set('Europe/Zurich');

// init
$app = new Silex\Application();

// default config
$app['redis.config'] = false; // array('host' => 'localhost', 'port' => 6379);

/// load config
$config = __DIR__.'/../config.php';
if (stream_resolve_include_path($config)) {
	include $config;
}

// twig
$app->register(new Silex\Provider\TwigServiceProvider(), array(
    'twig.path'       => __DIR__.'/../views',
    'twig.class_path' => __DIR__.'/../vendor/twig/lib',
));

if ($app['redis.config']) {
	$app['redis'] = new Predis\Client($app['redis.config']);
	$app['stats'] = new Transport\Statistics($app['redis']);

	// home
	$app->get('/', function(Request $request) use ($app) {

        // Redis text response
        if ($request->get('format') == 'txt') {

            $keys = $app['redis']->keys('stats:*');
            $values = $app['redis']->mget($keys);
            $data = array_combine($keys, $values);

            $txt = "MSET ";
            foreach ($data as $key => $value) {
                $txt .= "$key $value ";
            }
            return new Response($txt, 200, array('Content-Type' => 'text/plain'));
        }

	    $calls = $app['stats']->getCalls();

	    // transform to comma and new line separated list
	    $data = array();
	    foreach (array_slice($calls, -30) as $date => $value) {
	        $data[] = $date . ',' . ($value ?: 0);
	    }
	    $data = implode('\n', $data);

        // get top resources and stations
        $resources = $app['stats']->getTopResources();
        $stations = $app['stats']->getTopStations();

        // CSV response
        if ($request->get('format') == 'csv') {
            $csv = "Date,Calls\n";
            foreach ($calls as $date => $count) {
                $csv .= "$date,$count\n";
            }
            return new Response($csv, 200, array('Content-Type' => 'text/csv', 'Content-Disposition' => 'attachment;filename=transport.csv'));
        }

        // JSON response
        if ($request->get('format') == 'json') {
            return $app->json(array('calls' => $calls));
        }

	    // transform to comma and new line separated list
	    $data = array();
	    foreach (array_slice($calls, -30) as $date => $value) {
	        $data[] = $date . ',' . ($value ?: 0);
	    }
	    $data = implode('\n', $data);

	    return $app['twig']->render('stats.twig', array(
	        'data' => $data,
	        'calls' => $calls,
	        'resources' => $resources,
	        'stations' => $stations,
	    ));
	});
} else {
    $app->get('/', function(Request $request) use ($app) {
        return 'No Redis configured. See section "Statistics" in README.md.';
    });
}


// run
$app->run(); 
