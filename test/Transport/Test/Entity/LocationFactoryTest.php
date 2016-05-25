<?php

namespace Transport\Test\Entity;

use Transport\Entity\Coordinate;
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

    public function testCreateFromJson()
    {
        $jsonString = <<<'EOF'
{
    "extId": "8508489", 
    "name": "Nummerland", 
    "prodclass": "16",
    "puic": "85", 
    "urlname": "Nummerland", 
    "x": "8382324", 
    "y": "47003057"
}
EOF;
        $station = new Station();
        $station->name = 'Nummerland';
        $station->id = '8508489';
        $coordinate = new Coordinate();
        $coordinate->type = 'WGS84';
        $coordinate->x = 47.003057;
        $coordinate->y = 8.382324;
        $station->coordinate = $coordinate;
        $this->assertEquals($station, LocationFactory::createFromJson(json_decode($jsonString)));
    }

    public function testCreateFromJsonWithUmlaute()
    {
        $jsonString = <<<'EOF'
{
    "extId": "8508489", 
    "name": "N&#252;mmerland", 
    "prodclass": "16",
    "puic": "85", 
    "urlname": "N%FCmmerland", 
    "x": "8382324", 
    "y": "47003057"
}
EOF;
        $station = new Station();
        $station->name = 'Nümmerland';
        $station->id = '8508489';
        $coordinate = new Coordinate();
        $coordinate->type = 'WGS84';
        $coordinate->x = 47.003057;
        $coordinate->y = 8.382324;
        $station->coordinate = $coordinate;
        $this->assertEquals($station, LocationFactory::createFromJson(json_decode($jsonString)));
    }
}
