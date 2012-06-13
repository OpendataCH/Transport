<?php

require_once 'phar://'.__DIR__.'/../silex.phar'; 

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

// autoload
$app['autoloader']->registerNamespace('Predis', __DIR__.'/../vendor/predis/lib');


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
	    foreach ($calls as $date => $value) {
	        $data[] = $date . ',' . ($value ?: 0);
	    }
	    $data = implode('\n', $data);

        // JSON response
        if ($request->get('format') == 'json') {
            return json_encode(array('calls' => $calls));
        }

	    return $app['twig']->render('stats.twig', array(
	        'calls' => $calls,
	        'data' => $data,
	    ));
	});
}


// run
$app->run(); 
