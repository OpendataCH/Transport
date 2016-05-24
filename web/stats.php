<?php

require __DIR__.'/../vendor/autoload.php';

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
$app->register(new Silex\Provider\TwigServiceProvider(), [
    'twig.path'       => __DIR__.'/../views',
]);

if ($app['redis.config']) {
    $app['redis'] = new Predis\Client($app['redis.config']);
    $app['stats'] = new Transport\Statistics($app['redis']);

    // home
    $app->get('/', function (Request $request) use ($app) {

        $calls = $app['stats']->getCalls();
        $errors = $app['stats']->getErrors();

        // combine calls and errors
        $data = [];
        foreach ($calls as $date => $value) {
            $data[$date] = ['date' => $date, 'calls' => ((int) $value ?: 0), 'errors' => 0];
        }
        foreach ($errors as $date => $value) {
            if (isset($data[$date])) {
                $data[$date]['errors'] = ((int) $value ?: 0);
            }
        }
        $data = array_values($data);

        // CSV response
        if ($request->get('format') == 'csv') {
            $flat = [];
            foreach ($data as $value) {
                $flat[] = implode(',', $value);
            }

            $csv = "Date,Calls,Errors\n";
            $csv .= implode("\n", $flat);

            return new Response($csv, 200, ['Content-Type' => 'text/csv', 'Content-Disposition' => 'attachment;filename=transport.csv']);
        }

        // JSON response
        if ($request->get('format') == 'json') {
            return $app->json(['data' => $data]);
        }

        $total = array_sum($calls);
        $avg = $total / count($calls);
        $max = max($calls);

        // get top resources, stations and errors
        $resources = $app['stats']->getTopResources();
        $stations = $app['stats']->getTopStations();
        $errors = $app['stats']->getTopExceptions();

        return $app['twig']->render('stats.twig', [
            'total'     => $total,
            'avg'       => $avg,
            'max'       => $max,
            'calls'     => $calls,
            'resources' => $resources,
            'stations'  => $stations,
            'errors'    => $errors,
        ]);
    });
} else {
    $app->get('/', function (Request $request) use ($app) {
        return 'No Redis configured. See section "Statistics" in README.md.';
    });
}

// run
$app->run();
