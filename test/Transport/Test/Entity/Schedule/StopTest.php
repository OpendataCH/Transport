<?php

namespace Transport\Test\Entity\Schedule;

use Transport\Entity\Schedule\Stop;

class StopTest extends \PHPUnit_Framework_TestCase
{
    public function testParseDateTimeOffset()
    {
        $this->assertEquals('2012-03-31T13:03:59+02:00', Stop::calculateDateTime('01d13:03:59', '2012-03-30'));
    }

    public function testParseDateTimeNoOffset()
    {
        $this->assertEquals('2012-03-30T13:03:59+02:00', Stop::calculateDateTime('00d13:03:59', '2012-03-30'));
    }

    public function testParseDateTimeNoPrefix()
    {
        $this->assertEquals('2012-03-30T13:03:59+02:00', Stop::calculateDateTime('13:03:59', '2012-03-30'));
    }
}

