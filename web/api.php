<?php

require __DIR__.'/../vendor/autoload.php';

date_default_timezone_set('Europe/Zurich');

Symfony\Component\Debug\ErrorHandler::register();

// init
$app = new Transport\Application();

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
