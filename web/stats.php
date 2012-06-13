<?php

require_once __DIR__.'/../silex.phar'; 

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

	    // read last 30 days
	    $dates = array();
	    $keys = array();
	    for ($i = 30; $i >= 0; $i--) {
	        $date = date('Y-m-d', strtotime("-$i days"));
	        $keys[] = "stats:calls:$date";
	        $dates[] = $date;
	    }
	    $values = array_combine($dates, $app['redis']->mget($keys));

	    // transform to comma and new line separated list
	    $data = array();
	    foreach ($values as $date => $value) {
	        $data[] = $date . ',' . ($value ?: 0);
	    }
	    $data = implode('\n', $data);

	    return $app['twig']->render('stats.twig', array(
	        'values' => $values,
	        'data' => $data,
	    ));
	});
}


// run
$app->run(); 
