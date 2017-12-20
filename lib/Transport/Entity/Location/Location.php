<?php

namespace Transport\Entity\Location;

use Transport\Entity\Coordinate;

/**
 * @SWG\Definition()
 */
abstract class Location
{
    /**
     * The name of this location.
     *
     * @var string
     * @SWG\Property()
     */
    public $name;

    /**
     * The score with regard to the search request, the higher the better.
     *
     * @var int
     * @SWG\Property()
     */
    public $score;

    /**
     * The location coordinates.
     *
     * @var Coordinate
     * @SWG\Property()
     */
    public $coordinate;

    /**
     * If search has been with coordinates, distance to original point in meters.
     *
     * @var float
     * @SWG\Property()
     */
    public $distance;

    /**
     * Factory method to create an instance and extract the data from the given xml.
     *
     * @param \SimpleXMLElement $xml The item xml
     * @param Location          $obj An object or null to create it
     *
     * @return Location The created instance
     */
    public static function createFromXml(\SimpleXMLElement $xml, self $obj = null)
    {
        if (!is_object($obj)) {
            throw new \InvalidArgumentException('Argument must be an object');
        }

        if ($xml['name']) {
            $obj->name = (string) $xml['name'];
        }
        if ($xml['score']) {
            $obj->score = (int) $xml['score'];
        }
        $obj->coordinate = Coordinate::createFromXml($xml);

        return $obj;
    }

    /**
     * Factory method to create an instance and extract the data from the given JSON object.
     *
     * @param object   $json The item JSON
     * @param Location $obj  An object or null to create it
     *
     * @return Location The created instance
     */
    public static function createFromJson($json, self $obj = null)
    {
        if (!is_object($obj)) {
            throw new \InvalidArgumentException('Argument must be an object');
        }

        if (isset($json->text)) {
            $obj->name = $json->text;
        }

        if (isset($json->label)) {
            $obj->name = $json->label;
        }

        if (isset($json->name)) {
            $obj->name = $json->name;
        }

        if (isset($json->terminal->id)) {
            $obj->id = $json->terminal->id;
        }

        $obj->coordinate = Coordinate::createFromJson($json);

        if (isset($json->dist)) {
            $obj->distance = $json->dist;
        }

        return $obj;
    }

    /**
     * Convert to XML representation.
     *
     * @return \SimpleXMLElement
     */
    abstract public function toXml(\SimpleXMLElement $parent = null);
}
