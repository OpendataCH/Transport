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
            return Location\Station::createStationFromXml($xml);
        case 'Address':
            return Location\Address::createFromXml($xml);
        case 'ReqLoc':
        case 'Err':
        default:
            return;
        }
    }

    public static function createFromJson($json)
    {
        return Location\Station::createStationFromJson($json);
    }
}
