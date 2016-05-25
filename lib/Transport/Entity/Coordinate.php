<?php

namespace Transport\Entity;

/**
 * @SWG\Definition()
 */
class Coordinate
{
    /**
     * The type of the given coordinate.
     *
     * @var string
     * @SWG\Property()
     */
    public $type;

    /**
     * Latitude.
     *
     * @var float
     * @SWG\Property()
     */
    public $x;

    /**
     * Longitude.
     *
     * @var float
     * @SWG\Property()
     */
    public $y;

    /**
     * Factory method to create an instance of Coordinate and extract the data from the given xml.
     *
     * @param \SimpleXMLElement $xml The item xml
     *
     * @return Coordinate The created instance
     */
    public static function createFromXml(\SimpleXMLElement $xml)
    {
        $coordinate = new self();
        $coordinate->type = (string) $xml['type'];

        $x = self::intToFloat((string) $xml['x']);
        $y = self::intToFloat((string) $xml['y']);

        $coordinate = self::setHAFAScoordinates($coordinate, $x, $y);

        return $coordinate;
    }

    public static function createFromJson($json)
    {
        $coordinate = new self();
        $coordinate->type = 'WGS84'; // best guess

        $x = self::intToFloat($json->x);
        $y = self::intToFloat($json->y);

        $coordinate = self::setHAFAScoordinates($coordinate, $x, $y);

        return $coordinate;
    }

    public static function setHAFAScoordinates($coordinate, $x, $y)
    {
        if ($y > $x) { // HAFAS bug, returns inverted lat/long
          $coordinate->x = $y;
            $coordinate->y = $x;
        } else {
            $coordinate->x = $x;
            $coordinate->y = $y;
        }

        return $coordinate;
    }

    public static function floatToInt($float)
    {
        return sprintf('%01.6f', $float) * 1000000;
    }

    public static function intToFloat($int)
    {
        return $int / 1000000;
    }

    /**
     * Calculates the distance to another coordinate using the Haversine Formula.
     * Not really accurate.
     *
     * @return float
     */
    public function getDistanceTo($lat, $lon)
    {
        $earth_radius = 6371;

        $dLat = deg2rad($this->x - $lat);
        $dLon = deg2rad($this->y - $lon);

        $a = sin($dLat / 2) * sin($dLat / 2) + cos(deg2rad($lat)) * cos(deg2rad($this->y)) * sin($dLon / 2) * sin($dLon / 2);
        $c = 2 * asin(sqrt($a));
        $d = $earth_radius * $c;

        return round($d * 1000, 1);
    }
}
