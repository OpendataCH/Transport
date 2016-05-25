<?php

namespace Transport\Test\Entity\Location;

use Transport\Entity\Coordinate;
use Transport\Entity\Location\Station;

class StationTest extends \PHPUnit_Framework_TestCase
{
    protected function getStation()
    {
        $station = new Station('008508051');
        $station->name = 'Bern Felsenau';
        $station->score = 81;
        $coordinate = new Coordinate();
        $coordinate->type = 'WGS84';
        $coordinate->x = 46.968493;
        $coordinate->y = 7.444245;
        $station->coordinate = $coordinate;

        return $station;
    }

    public function testToXml()
    {
        $this->assertXmlStringEqualsXmlString('<Station name="Bern Felsenau" externalId="008508051"/>', $this->getStation()->toXml()->asXml());
    }

    public function testCreateFromXmlStation()
    {
        $xml = new \SimpleXMLElement('<Station name="Bern Felsenau" score="81" externalId="008508051#95" externalStationNr="008508051" type="WGS84" x="7444245" y="46968493"/>');

        $this->assertEquals($this->getStation(), Station::createStationFromXml($xml));
    }
}
