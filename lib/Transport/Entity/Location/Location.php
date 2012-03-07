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
     * @param   \SimpleXmlElement   $parent     The parent element or null to create a new one
     * @return  \SimpleXMLElement
     */
    public function toXml(\SimpleXMLElement $parent = null)
    {
        // could be improved :)
        $className = substr(get_class($this), strlen(__NAMESPACE__) + 1);

        if (null !== $parent) {
            $xml = $parent->addChild($className);
        } else {
            $xml = new \SimpleXMLElement(sprintf('<%s />', $className));
        }

        $xml->addAttribute('name', $this->name);
        $xml->addAttribute('x', $this->coordinate->x);
        $xml->addAttribute('y', $this->coordinate->y);
        return $xml;
    }

    /**
     * Factory method to create an instance and extract the data from the given xml
     *
     * @param   \SimpleXMLElement   $xml    The item xml
     * @param   Location            $obj    An object or null to create it
     * @return  Location            The created instance
     */
    static public function createFromXml(\SimpleXMLElement $xml, Location $obj = null)
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
}
