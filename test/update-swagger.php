<?php

require_once 'bootstrap.php';

$app = new Transport\Application();
$client = new Symfony\Component\HttpKernel\Client($app);

$client->request('GET', '/swagger.json');

file_put_contents(__DIR__.'/fixtures/swagger.json', $client->getResponse()->getContent());
