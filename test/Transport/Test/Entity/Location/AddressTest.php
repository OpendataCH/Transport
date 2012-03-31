<?php

namespace Transport\Test\Entity\Location;

use Transport\Entity\Location\Address;
use Transport\Entity\Coordinate;

class AddressTest extends \PHPUnit_Framework_TestCase
{
    protected function getAddress()
    {
        $address = new Address;
        $address->name = '3011 Bern, Bollwerk 19';
        $coordinate = new Coordinate();
        $coordinate->type = 'WGS84';
        $coordinate->x = 7.440803;
        $coordinate->y = 46.949607;
        $address->coordinate = $coordinate;

        return $address;
    }

    public function testCreateFromXml()
    {
        $xml = new \SimpleXMLElement('<Address name="3011 Bern, Bollwerk 19" type="WGS84" x="7440803" y="46949607"/>');

        $this->assertEquals($this->getAddress(), Address::createFromXml($xml));
    }
}

