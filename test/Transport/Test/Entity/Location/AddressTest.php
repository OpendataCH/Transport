<?php

namespace Transport\Test\Entity\Location;

use Transport\Entity\Coordinate;
use Transport\Entity\Location\Address;

class AddressTest extends \PHPUnit\Framework\TestCase
{
    protected function getAddress()
    {
        $address = new Address();
        $address->name = '3011 Bern, Bollwerk 19';
        $coordinate = new Coordinate();
        $coordinate->type = 'WGS84';
        $coordinate->x = 46.949607;
        $coordinate->y = 7.440803;
        $address->coordinate = $coordinate;

        return $address;
    }

    public function testCreateFromXml()
    {
        $xml = new \SimpleXMLElement('<Address name="3011 Bern, Bollwerk 19" type="WGS84" x="7440803" y="46949607"/>');

        $this->assertEquals($this->getAddress(), Address::createFromXml($xml));
    }

    public function testToXml()
    {
        $this->assertXmlStringEqualsXmlString('<Address name="3011 Bern, Bollwerk 19" y="46949607" x="7440803"/>', $this->getAddress()->toXml()->asXml());
    }
}
