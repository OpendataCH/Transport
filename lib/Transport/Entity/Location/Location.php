<?php

namespace Transport\Entity\Location;

use Transport\Entity\Coordinate;

class Location
{
    /**
     * The name of this location
     * @var string
     */
    public $name;

    /**
     * The score with regard to the search request, the higher the better
     * @var int
     */
    public $score;

    /**
     * @var Coordinate
     */
    public $coordinate;

    /**
     * @var int
     */
    public $distance;

    /**
     * Factory method to create an instance and extract the data from the given xml
     *
     * @param   \SimpleXMLElement   $xml    The item xml
     * @param   Location            $obj    An object or null to create it
     * @return  Location            The created instance
     */
    public static function createFromXml(\SimpleXMLElement $xml, Location $obj = null)
    {
        if (!is_object($obj)) {
            throw new \InvalidArgumentException('Argument must be an object');
        }

        if ($xml['name']) {
            $obj->name = (string) $xml['name'];
        }
        if ($xml['score']) {
            $obj->score = (string) $xml['score'];
        }
        $obj->coordinate = Coordinate::createFromXml($xml);

        return $obj;
    }

    /**
     * Factory method to create an instance and extract the data from the given JSON object
     *
     * @param   object     $json  The item JSON
     * @param   Location   $obj    An object or null to create it
     * @return  Location           The created instance
     */
    public static function createFromJson($json, Location $obj = null)
    {
        if (!is_object($obj)) {
            throw new \InvalidArgumentException('Argument must be an object');
        }

        if ($json->name) {
            $obj->name = html_entity_decode($json->name, null, 'UTF-8');
        }
        $obj->coordinate = Coordinate::createFromJson($json);

        return $obj;
    }
}
