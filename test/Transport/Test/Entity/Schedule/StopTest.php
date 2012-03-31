<?php

namespace Transport\Test\Entity\Schedule;

use Transport\Entity\Schedule\Stop;

class StopTest extends \PHPUnit_Framework_TestCase
{
    public function testParseTimePrefix()
    {
        $this->assertEquals('13:03:59', Stop::parseTime('00d13:03:59'));
    }

    public function testParseTimePrefixOffset()
    {
        $this->assertEquals('13:03:59', Stop::parseTime('01d13:03:59'));
    }

    public function testParseTimeNoPrefix()
    {
        $this->assertEquals('13:03:59', Stop::parseTime('13:03:59'));
    }

    public function testParseDateOffset()
    {
        $this->assertEquals('2012-03-31', Stop::parseDate('01d13:03:59', '2012-03-30'));
    }

    public function testParseDateNoOffset()
    {
        $this->assertEquals('2012-03-30', Stop::parseDate('00d13:03:59', '2012-03-30'));
    }

    public function testParseDateNoPrefix()
    {
        $this->assertEquals('2012-03-30', Stop::parseDate('13:03:59', '2012-03-30'));
    }
}

