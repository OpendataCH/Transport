<?php

// Debug
$app['debug'] = true;

// HTTP Cache
$app['http_cache'] = false;

// Log level
$app['monolog.level'] = Monolog\Logger::ERROR;

// Redis for statistics
$app['redis.config'] = false; // array('host' => 'localhost', 'port' => 9464);
