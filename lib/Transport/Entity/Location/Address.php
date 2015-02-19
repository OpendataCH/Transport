<?php

namespace Transport\Entity\Location;

use Transport\Entity\Coordinate;

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
    public function toXml(\SimpleXMLElement $parent = null)
    {
        if (null !== $parent) {
            $xml = $parent->addChild('Address');
        } else {
            $xml = new \SimpleXMLElement('<Address />');
        }

        $xml['name'] = $this->name;

        // x and y inverted for HAFAS
        if ($this->coordinate->x) {
            $xml['y'] = Coordinate::floatToInt($this->coordinate->x);
        }
        if ($this->coordinate->y) {
            $xml['x'] = Coordinate::floatToInt($this->coordinate->y);
        }

        return $xml;
    }

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

