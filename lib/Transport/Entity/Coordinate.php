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
        $coordinate->x = self::intToFloat((string) $xml['x']);
        $coordinate->y = self::intToFloat((string) $xml['y']);

        return $coordinate;
    }

    static public function createFromJson($json)
    {
        $coordinate = new Coordinate();
        $coordinate->type = 'WGS84'; // best guess
        $coordinate->x = self::intToFloat($json->x);
        $coordinate->y = self::intToFloat($json->y);

        return $coordinate;
    }

    static public function floatToInt($float)
    {
        return sprintf('%01.6f', $float) * 1000000;
    }

    static public function intToFloat($int)
    {
        return $int / 1000000;
    }

    /**
     * Calculates the distance to another coordinate using the Haversine Formula.
     * Not really accurate.
     */
    public function getDistanceTo($lat, $lon)
    {
        $earth_radius = 6371;

        $dLat = deg2rad($this->y - $lat);
        $dLon = deg2rad($this->x - $lon);  

        $a = sin($dLat/2) * sin($dLat/2) + cos(deg2rad($lat)) * cos(deg2rad($this->y)) * sin($dLon/2) * sin($dLon/2);  
        $c = 2 * asin(sqrt($a));
        $d = $earth_radius * $c;

        return round($d*1000, 1);
    }
}
