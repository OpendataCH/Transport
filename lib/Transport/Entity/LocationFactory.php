<?php

namespace Transport\Entity;

class LocationFactory
{
    static public function createFromXml(\SimpleXMLElement $xml)
    {
        switch ($xml->getName()) {
        case 'Poi':
            return Location\Poi::createFromXml($xml);
        case 'Station':
            return Location\Station::createFromXml($xml);
        case 'Address':
            return Location\Address::createFromXml($xml);
        case 'ReqLoc':
        case 'Err':
            return null;
        default:
        }

        throw new \Exception('Unknown entity type: '.$xml->getName());
    }
}
