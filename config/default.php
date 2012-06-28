<?php

// Debug
$app['debug'] = true;

// HTTP Cache
$app['http_cache'] = false;

// Buzz client, null uses Buzz\Client\FileGetContents
$app['buzz.client'] = null;

// Log level
$app['monolog.level'] = Monolog\Logger::ERROR;

// XHProf for profiling
$app['xhprof'] = false;

// Redis for statistics
$app['redis.config'] = false; // array('host' => 'localhost', 'port' => 9464);

// if hosted behind a reverse proxy
$app['proxy'] = false;
