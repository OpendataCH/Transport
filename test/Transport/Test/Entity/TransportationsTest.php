<?php

namespace Transport\Test\Entity;

use Transport\Entity\Transportations;

class TransportationsTest extends \PHPUnit_Framework_TestCase
{
    public function testReduceTransportations()
    {
        $transportations = ['bus', 'ship'];

        $this->assertSame('0000101000000000', Transportations::reduceTransportations($transportations));
    }

    public function testReduceTransportationsTrain()
    {
        $transportations = ['ice_tgv_rj'];

        $this->assertSame('1000000000000000', Transportations::reduceTransportations($transportations));
    }

    public function testReduceTransportationsAll()
    {
        $transportations = ['all'];

        $this->assertSame('1111111111111111', Transportations::reduceTransportations($transportations));
    }

    public function testReduceTransportationsDec()
    {
        $transportations = ['bus', 'ship'];

        $this->assertSame(80, Transportations::reduceTransportationsDec($transportations));
    }

    public function testReduceTransportationsDecTrain()
    {
        $transportations = ['ice_tgv_rj'];

        $this->assertSame(1, Transportations::reduceTransportationsDec($transportations));
    }

    public function testReduceTransportationsDecAll()
    {
        $transportations = ['all'];

        $this->assertSame(65535, Transportations::reduceTransportationsDec($transportations));
    }

    public function testReduceTransportationsDecAllTen()
    {
        $transportations = ['all'];

        $this->assertSame(1023, Transportations::reduceTransportationsDec($transportations, 10));
    }
}
