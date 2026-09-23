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
        // errors, calls and rate-limited requests of one time window
        if ($request->get('format') == 'window') {
            return $app->json(statsWindow($app['stats'], $request->get('window')));
        }

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

        return $app['twig']->render('stats.twig', [
            'total'     => $total,
            'avg'       => $avg,
            'max'       => $max,
            'calls'     => $calls,
            'resources' => $resources,
            'stations'  => $stations,
            'errors'    => $errors,
            'windows'   => statsWindows(),
            'window'    => statsWindow($app['stats'], 'all'),
        ]);
    });
} else {
    $app->get('/', function () {
        return 'No Redis configured. See section "Statistics" in README.md.';
    });
}

/**
 * The time windows the error details can be narrowed to, key => label.
 *
 * @return array
 */
function statsWindows()
{
    return [
        '1h'  => 'Last hour',
        '2h'  => 'Last 2 hours',
        '6h'  => 'Last 6 hours',
        '12h' => 'Last 12 hours',
        '24h' => 'Last 24 hours',
        '48h' => 'Last 48 hours',
        '7d'  => 'Last 7 days',
        '14d' => 'Last 14 days',
        '30d' => 'Last 30 days',
        'all' => 'Since 2015',
    ];
}

/**
 * What the kinds of client in Statistics::CLIENT_KINDS are called on the page.
 *
 * @return array
 */
function statsClientKinds()
{
    return [
        'homeassistant'   => 'Home Assistant',
        'browser'         => 'Browsers and displays',
        'script'          => 'Scripts and servers',
        'microcontroller' => 'Microcontrollers (ESP32 …)',
        'app'             => 'Mobile apps',
        'none'            => 'No user agent',
        'other'           => 'Other',
    ];
}

/**
 * Errors by class, and calls, errors and rate-limited requests over time, for one window.
 *
 * Hour windows are read from the hourly buckets alone. Day windows are calendar days: calls
 * and errors come from the daily counters, which go back to 2012; the split by error class
 * and the rate-limited requests only exist in the hourly buckets. "all" uses the all-time
 * totals by class and lists the last 14 days.
 *
 * @param Transport\Statistics $stats
 * @param string               $window a key of statsWindows()
 *
 * @return array
 */
function statsWindow(Transport\Statistics $stats, $window)
{
    if (!array_key_exists($window, statsWindows())) {
        $window = '24h';
    }

    $unit = substr($window, -1);
    $size = (int) $window;

    if ($unit == 'h') {
        $buckets = $stats->getHourly($size);
        $rows = [];
        foreach ($buckets as $bucket) {
            $rows[] = [
                'start'       => $bucket['hour'],
                'calls'       => $bucket['recorded'] ? $bucket['calls'] : null,
                'errors'      => $bucket['recorded'] ? $bucket['errors'] : null,
                'ratelimited' => $bucket['recorded'] ? $bucket['ratelimited'] : null,
            ];
        }
    } else {
        $days = $window == 'all' ? 14 : $size;
        $hoursToday = (int) date('G') + 1;
        $buckets = $stats->getHourly(($days - 1) * 24 + $hoursToday);
        $daily = $stats->getDays($days);

        // rate-limited requests per day, where the day has hourly buckets
        $ratelimited = [];
        foreach ($buckets as $bucket) {
            $date = substr($bucket['hour'], 0, 10);
            if ($bucket['recorded']) {
                $ratelimited[$date] = (isset($ratelimited[$date]) ? $ratelimited[$date] : 0) + $bucket['ratelimited'];
            }
        }

        $rows = [];
        foreach ($daily as $date => $day) {
            $rows[] = [
                'start'       => $date,
                'calls'       => $day['calls'],
                'errors'      => $day['errors'],
                'ratelimited' => isset($ratelimited[$date]) ? $ratelimited[$date] : null,
            ];
        }
    }

    // errors by class
    $byClass = [];
    if ($window == 'all') {
        foreach ($stats->getExceptions() as $exception) {
            $byClass[$exception['exception']] = (int) $exception['calls'];
        }
    } else {
        foreach ($buckets as $bucket) {
            foreach ($bucket['exceptions'] as $class => $count) {
                $byClass[$class] = (isset($byClass[$class]) ? $byClass[$class] : 0) + $count;
            }
        }
        arsort($byClass);
    }
    $classTotal = array_sum($byClass);
    $exceptions = [];
    foreach ($byClass as $class => $count) {
        $exception = describeException(['exception' => $class, 'calls' => $count]);
        $exception['share'] = $classTotal > 0 ? 100 * $count / $classTotal : 0;
        $exceptions[] = $exception;
    }

    // the calendar days the window touches, oldest first
    $dates = [];
    if ($unit == 'h') {
        foreach ($buckets as $bucket) {
            $dates[substr($bucket['hour'], 0, 10)] = true;
        }
        $dates = array_keys($dates);
    } else {
        $dates = array_keys($daily);
    }

    // requests by kind of client, rate-limited ones included
    $kinds = [];
    foreach ($buckets as $bucket) {
        foreach ($bucket['clients'] as $kind => $count) {
            $kinds[$kind] = (isset($kinds[$kind]) ? $kinds[$kind] : 0) + $count;
        }
    }
    arsort($kinds);
    $kindsTotal = array_sum($kinds);
    $clientKinds = [];
    foreach ($kinds as $kind => $count) {
        $clientKinds[] = [
            'kind'     => $kind,
            'label'    => isset(statsClientKinds()[$kind]) ? statsClientKinds()[$kind] : $kind,
            'requests' => $count,
            'share'    => $kindsTotal > 0 ? 100 * $count / $kindsTotal : 0,
        ];
    }

    // average calls per hour of the day, over the hours that were recorded
    $profileSums = array_fill(0, 24, 0);
    $profileHours = array_fill(0, 24, 0);
    foreach ($buckets as $bucket) {
        if ($bucket['recorded']) {
            $hourOfDay = (int) substr($bucket['hour'], 11, 2);
            $profileSums[$hourOfDay] += $bucket['calls'] + $bucket['ratelimited'];
            $profileHours[$hourOfDay]++;
        }
    }
    $profile = [];
    foreach ($profileSums as $hourOfDay => $sum) {
        $profile[] = $profileHours[$hourOfDay] > 0 ? (int) round($sum / $profileHours[$hourOfDay]) : null;
    }

    $top = function ($kind) use ($stats, $dates) {
        $result = [];
        foreach ($stats->getTop($kind, $dates) as $name => $requests) {
            // PHP turns a numeric member such as a stop id into an integer key.
            $result[] = ['name' => (string) $name, 'requests' => (int) $requests];
        }

        return $result;
    };

    $clientDays = [];
    foreach ($stats->getClientDays($dates) as $date => $summary) {
        $clientDays[] = ['date' => $date] + $summary;
    }

    // first hour of the window with an hourly bucket, if any
    $since = null;
    foreach ($buckets as $bucket) {
        if ($bucket['recorded']) {
            $since = $bucket['hour'];
            break;
        }
    }

    $calls = array_sum(array_column($rows, 'calls'));
    $errors = array_sum(array_column($rows, 'errors'));

    return [
        'window'      => $window,
        'label'       => statsWindows()[$window],
        'granularity' => $unit == 'h' ? 'hour' : 'day',
        'since'       => $since,
        'calls'       => $calls,
        'errors'      => $errors,
        'ratelimited' => $since === null ? null : array_sum(array_filter(array_column($rows, 'ratelimited'))),
        'classTotal'  => $classTotal,
        'exceptions'  => $exceptions,
        'rows'        => array_reverse($rows),
        'clientKinds' => $clientKinds,
        'kindsTotal'  => $kindsTotal,
        'clientDays'  => array_reverse($clientDays),
        'stations'    => $top('stations'),
        'routes'      => $top('routes'),
        'profile'     => $profile,
    ];
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
        'TypeError'                                                            => ['500', 'A single value where the API expects a list, e.g. fields= without brackets'],
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
