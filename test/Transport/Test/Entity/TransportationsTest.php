<?php

namespace Transport\Test\Entity;

use Transport\Entity\Transportations;

class APITest extends \PHPUnit_Framework_TestCase
{
    public function testReduceTransportations()
    {
        $transportations = array('bus', 'ship');

        $this->assertSame('0000101000000000', Transportations::reduceTransportations($transportations));
    }
}
