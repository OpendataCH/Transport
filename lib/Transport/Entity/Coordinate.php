<?php

namespace Transport\Entity;

class Coordinate
{
    /**
     * @var string
     */
    public $type;

    /**
     * @var int
     */
    public $x;

    /**
     * @var int
     */
    public $y;

    /**
     * Factory method to create an instance of Coordinate and extract the data from the given xml
     *
     * @param   \SimpleXMLElement   $xml    The item xml
     * @return  Coordinate          The created instance
     */
    static public function createFromXml(\SimpleXMLElement $xml)
    {
        $coordinate = new Coordinate();
        $coordinate->type = (string) $xml['type'];
        $coordinate->x = (string) $xml['x'];
        $coordinate->y = (string) $xml['y'];

        return $coordinate;
    }

    static public function createFromJson($json)
    {
        $coordinate = new Coordinate();
        $coordinate->type = 'WGS84'; // best guess
        $coordinate->x = $json->x;
        $coordinate->y = $json->y;

        return $coordinate;
    }
}
