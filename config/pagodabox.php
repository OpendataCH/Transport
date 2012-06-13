<?php

$app['debug'] = true;
$app['http_cache'] = true;

$app['redis.config'] = array('host' => $_SERVER['CACHE1_HOST'], 'port' => $_SERVER['CACHE1_PORT']);
