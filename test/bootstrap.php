<?php

date_default_timezone_set('Europe/Zurich');

use SebastianBergmann\Comparator\Factory;
use Transport\Test\PhpUnit\XmlComparator;

require __DIR__ . '/../vendor/autoload.php';

Factory::getInstance()->register(new XmlComparator());
