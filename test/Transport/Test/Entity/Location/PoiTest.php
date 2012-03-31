<?php

namespace Transport\Test\Entity\Location;

use Transport\Entity\Location\Poi;
use Transport\Entity\Coordinate;

class PoiTest extends \PHPUnit_Framework_TestCase
{
    protected function getPoi()
    {
        $poi = new Poi;
        $poi->name = 'Ittigen, Bahnhof';
        $poi->score = '100';
        $coordinate = new Coordinate();
        $coordinate->type = 'WGS84';
        $coordinate->x = 7.478189;
        $coordinate->y = 46.976494;
        $poi->coordinate = $coordinate;

        return $poi;
    }

    public function testCreateFromXml()
    {
        $xml = new \SimpleXMLElement('<Poi name="Ittigen, Bahnhof" score="100" type="WGS84" x="7478189" y="46976494" />');

        $this->assertEquals($this->getPoi(), Poi::createFromXml($xml));
    }
}

