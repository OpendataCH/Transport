<?php

namespace Transport\Entity\Location;

/**
 * Represents a Poi we received as response
 *
 * <Poi name="Ittigen, Bahnhof" score="100" type="WGS84" x="7478189" y="46976494" />
 */
class Poi extends Location
{
    /**
     * {@inheritDoc}
     */
    static public function createFromXml(\SimpleXMLElement $xml, Location $obj = null)
    {
        if (!$obj) {
            $obj = new Poi;
        }
        return parent::createFromXml($xml, $obj);
    }
}

