<?php

require_once 'phar://'.__DIR__.'/../silex.phar'; 
require __DIR__ . '/../vendor/autoload.php';

use Symfony\Component\HttpFoundation\Request;
use Symfony\Component\HttpFoundation\Response;

date_default_timezone_set('Europe/Zurich');

// init
$app = new Silex\Application();

// load config
require __DIR__.'/../config/default.php';
$local = __DIR__.'/../config/local.php';
if (stream_resolve_include_path($local)) {
	$local = include $local;
}

// twig
$app->register(new Silex\Provider\TwigServiceProvider(), array(
    'twig.path'       => __DIR__.'/../views',
    'twig.class_path' => __DIR__.'/../vendor/twig/lib',
));

if ($app['redis.config']) {
	$app['redis'] = new Predis\Client($app['redis.config']);

	// home
	$app->get('/', function(Request $request) use ($app) {

	    $keys = $app['redis']->keys('stats:calls:*');
	    $values = $app['redis']->mget($keys);
	    $calls = array();
	    foreach ($keys as $i => $key) {
	        $calls[substr($key, 12, 10)] = $values[$i];
	    }
	    ksort($calls);

	    // transform to comma and new line separated list
	    $data = array();
	    foreach (array_slice($calls, -30) as $date => $value) {
	        $data[] = $date . ',' . ($value ?: 0);
	    }
	    $data = implode('\n', $data);

        // Redis text response
        if ($request->get('format') == 'txt') {
            $txt = "MSET ";
            foreach ($calls as $date => $count) {
                $txt .= "stats:calls:$date $count ";
            }
            return new Response($txt, 200, array('Content-Type' => 'text/plain'));
        }

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

	    return $app['twig']->render('stats.twig', array(
	        'calls' => $calls,
	        'data' => $data,
	    ));
	});
} else {
    $app->get('/', function(Request $request) use ($app) {
        return 'No Redis configured. See section "Statistics" in README.md.';
    });
}


// run
$app->run(); 
