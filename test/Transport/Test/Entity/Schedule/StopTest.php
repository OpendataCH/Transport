<?php

namespace Transport\Test\Entity\Schedule;

use Transport\Entity\Schedule\Stop;

class StopTest extends \PHPUnit_Framework_TestCase
{

    /**
     * @var \DateTime
     */
    private $date;

    public function setUp()
    {
        $this->date = \DateTime::createFromFormat('Y-m-d', '2012-03-30', new \DateTimeZone('Europe/Zurich'));
        $this->date->setTime(0, 0, 0);
    }

    public function testParseDateTimeOffset()
    {
        $this->assertEquals('2012-03-31T13:03:59+0200', Stop::calculateDateTime('01d13:03:59', $this->date)->format(\DateTime::ISO8601));
    }

    public function testParseDateTimeNoOffset()
    {
        $this->assertEquals('2012-03-30T13:03:59+0200', Stop::calculateDateTime('00d13:03:59', $this->date)->format(\DateTime::ISO8601));
    }

    public function testParseDateTimeNoPrefix()
    {
        $this->assertEquals('2012-03-30T13:03:59+0200', Stop::calculateDateTime('13:03:59', $this->date)->format(\DateTime::ISO8601));
    }
}

