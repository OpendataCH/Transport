<?php

// Debug
$app['debug'] = true;

// HTTP Cache
$app['http_cache'] = false;

// Log level
$app['monolog.level'] = Monolog\Logger::ERROR;

// XHProf for profilling
$app['xhprof'] = false;

// Redis for statistics
$app['redis.config'] = false; // array('host' => 'localhost', 'port' => 9464);

// if hosted behind a reverse proxy
$app['proxy'] = false;
