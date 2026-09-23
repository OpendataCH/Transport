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
        $avg = $total / max(count($calls), 1);
        $max = count($calls) > 0 ? max($calls) : 0;

        // get top resources, stations and errors
        $resources = $app['stats']->getTopResources();
        $stations = $app['stats']->getTopStations();
        $errors = array_map('describeException', $app['stats']->getTopExceptions());

        // all exception classes with their share of all recorded errors
        $exceptions = array_map('describeException', $app['stats']->getExceptions());
        $exceptionsTotal = array_sum(array_column($exceptions, 'calls'));
        foreach ($exceptions as &$exception) {
            $exception['share'] = $exceptionsTotal > 0 ? 100 * $exception['calls'] / $exceptionsTotal : 0;
        }
        unset($exception);

        // calls and errors of the last 14 days, newest first
        $days = [];
        foreach (array_slice(array_reverse($data), 0, 14) as $day) {
            $day['rate'] = $day['calls'] > 0 ? 100 * $day['errors'] / $day['calls'] : 0;
            $days[] = $day;
        }

        return $app['twig']->render('stats.twig', [
            'total'           => $total,
            'avg'             => $avg,
            'max'             => $max,
            'calls'           => $calls,
            'resources'       => $resources,
            'stations'        => $stations,
            'errors'          => $errors,
            'exceptions'      => $exceptions,
            'exceptionsTotal' => $exceptionsTotal,
            'days'            => $days,
        ]);
    });
} else {
    $app->get('/', function () {
        return 'No Redis configured. See section "Statistics" in README.md.';
    });
}

/**
 * Adds a short name, the HTTP status and a plain explanation to an exception counter.
 *
 * @param array $error ['exception' => class name, 'calls' => count]
 *
 * @return array
 */
function describeException(array $error)
{
    $known = [
        'Symfony\Component\HttpKernel\Exception\MethodNotAllowedHttpException' => ['405', 'Request used an HTTP method other than GET'],
        'Exception'                                                            => ['500', 'timetable.search.ch answered with a server error, an error message or invalid JSON'],
        'Buzz\Exception\RequestException'                                      => ['500', 'Connection to timetable.search.ch failed or timed out'],
        'Buzz\Exception\ClientException'                                       => ['500', 'HTTP client error while calling timetable.search.ch'],
        'Symfony\Component\Debug\Exception\ContextErrorException'              => ['500', 'PHP warning or notice inside the API (a bug)'],
        'Symfony\Component\HttpKernel\Exception\NotFoundHttpException'         => ['404', 'Unknown path'],
        'Symfony\Component\HttpKernel\Exception\BadRequestHttpException'       => ['400', 'Missing or invalid parameters'],
        'Symfony\Component\HttpKernel\Exception\HttpException'                 => ['4xx', 'Other HTTP error raised by the API'],
        'Predis\ClientException'                                               => ['500', 'Statistics store (Redis) rejected a command'],
        'Predis\Response\ServerException'                                      => ['500', 'Statistics store (Redis) returned an error'],
        'Predis\Connection\ConnectionException'                                => ['500', 'Statistics store (Redis) unreachable'],
    ];

    $class = $error['exception'];
    $position = strrpos($class, '\\');

    $error['name'] = $position === false ? $class : substr($class, $position + 1);
    $error['namespace'] = $position === false ? '' : substr($class, 0, $position);
    $error['status'] = isset($known[$class]) ? $known[$class][0] : '';
    $error['description'] = isset($known[$class]) ? $known[$class][1] : '';
    $error['calls'] = (int) $error['calls'];

    return $error;
}

// run
$app->run();
