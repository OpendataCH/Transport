<?php

namespace Transport\Test\Entity;

use Transport\Entity\Location\Station;
use Transport\Entity\LocationFactory;

class LocationFactoryTest extends \PHPUnit_Framework_TestCase
{
    public function testCreateFromXml_Poi()
    {
        $xml = new \SimpleXMLElement('<Poi />');
        $this->assertInstanceOf('Transport\Entity\Location\Poi', LocationFactory::createFromXml($xml));
    }

    public function testCreateFromXml_Station()
    {
        $xml = new \SimpleXMLElement('<Station />');
        $this->assertInstanceOf('Transport\Entity\Location\Station', LocationFactory::createFromXml($xml));
    }

    public function testCreateFromXml_Address()
    {
        $xml = new \SimpleXMLElement('<Address />');
        $this->assertInstanceOf('Transport\Entity\Location\Address', LocationFactory::createFromXml($xml));
    }

    public function testCreateFromXml_Unknown()
    {
        $xml = new \SimpleXMLElement('<YouDontKnowMe />');
        $this->assertNull(LocationFactory::createFromXml($xml));
    }
}
