<?php

namespace Transport\Test\Entity\Location;

use Transport\Entity\Coordinate;
use Transport\Entity\Location\Poi;

class PoiTest extends \PHPUnit\Framework\TestCase
{
    protected function getPoi()
    {
        $poi = new Poi();
        $poi->name = 'Ittigen, Bahnhof';
        $poi->score = 100;
        $coordinate = new Coordinate();
        $coordinate->type = 'WGS84';
        $coordinate->x = 46.976494;
        $coordinate->y = 7.478189;
        $poi->coordinate = $coordinate;

        return $poi;
    }

    public function testCreateFromXml()
    {
        $xml = new \SimpleXMLElement('<Poi name="Ittigen, Bahnhof" score="100" type="WGS84" x="7478189" y="46976494" />');

        $this->assertEquals($this->getPoi(), Poi::createFromXml($xml));
    }
}
