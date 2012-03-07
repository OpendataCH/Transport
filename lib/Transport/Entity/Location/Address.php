<?php

namespace Transport\Entity\Location;

/**
 * Represents a Address we received as response
 *
 * <Address name="3011 Bern, Bollwerk 19" type="WGS84" x="7440803" y="46949607"/>
 */
class Address extends Location
{
    /**
     * {@inheritDoc}
     */
    static public function createFromXml(\SimpleXMLElement $xml, Location $obj = null)
    {
        if (!$obj) {
            $obj = new Address;
        }
        return parent::createFromXml($xml, $obj);
    }
}

