<?php

namespace Transport\Test\Entity\Schedule;

use Transport\Entity\Schedule\Stop;

class StopTest extends \PHPUnit\Framework\TestCase
{
    /**
     * @var \DateTime
     */
    private $date;

    public function setUp(): void
    {
        $this->date = new \DateTime('2012-03-30T12:30:00+0200');
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

    public function testParseDateTimeMidnight()
    {
        $this->assertEquals('2012-03-31T00:30:00+0200', Stop::calculateDateTime('00:30', $this->date)->format(\DateTime::ISO8601));
    }
}
