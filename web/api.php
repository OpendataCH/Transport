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
