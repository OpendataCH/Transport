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
        $coordinate->type = 'WGS84';

        if (isset($json->x) && isset($json->y)) {
            $y = (int) $json->y;
            $x = (int) $json->x;

            // https://github.com/ValentinMinder/Swisstopo-WGS84-LV03/blob/master/scripts/php/wgs84_ch1903.php
            //
            // The MIT License (MIT)
            //
            // Copyright (c) 2014 Federal Office of Topography swisstopo, Wabern, CH
            //
            // Permission is hereby granted, free of charge, to any person obtaining a copy
            //  of this software and associated documentation files (the "Software"), to deal
            //  in the Software without restriction, including without limitation the rights
            //  to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
            //  copies of the Software, and to permit persons to whom the Software is
            //  furnished to do so, subject to the following conditions:
            //
            // The above copyright notice and this permission notice shall be included in
            //  all copies or substantial portions of the Software.
            //
            // THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
            //  IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
            //  FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
            //  AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
            //  LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
            //  OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
            //  THE SOFTWARE.
            //

            $y = ($y - 200000) / 1000000;
            $x = ($x - 600000) / 1000000;

            $lat = 16.9023892
               + 3.238272 * $y
               - 0.270978 * pow($x, 2)
               - 0.002528 * pow($y, 2)
               - 0.0447 * pow($x, 2) * $y
               - 0.0140 * pow($y, 3);

            $long = 2.6779094
               + 4.728982 * $x
               + 0.791484 * $x * $y
               + 0.1306 * $x * pow($y, 2)
               - 0.0436 * pow($x, 3);

            $coordinate->x = round($lat * 100 / 36, 6);
            $coordinate->y = round($long * 100 / 36, 6);
        }

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
        return ((int) $int) / 1000000;
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
