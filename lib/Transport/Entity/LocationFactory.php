<?php

namespace Transport\Entity;

class LocationFactory
{
    public static function createFromXml(\SimpleXMLElement $xml)
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
        default:
            return null;
        }
    }

    public static function createFromJson($json)
    {
        return Location\Station::createFromJson($json);
    }
}
