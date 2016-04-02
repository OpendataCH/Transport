<?php

namespace Transport\Entity\Location;

/**
 * Represents a station we received as response
 *
 * <Station name="Bern Felsenau" score="81" externalId="008508051#95" externalStationNr="008508051" type="WGS84" x="7444245" y="46968493"/>
 */
class Station extends Location
{
    /**
     * @var string
     */
    public $id;

    /**
     * @param string $id
     */
    public function __construct($id = null) {
        $this->id = $id;
    }

    /**
     * {@inheritDoc}
     */
    public function toXml(\SimpleXMLElement $parent = null)
    {
        if (null !== $parent) {
            $xml = $parent->addChild('Station');
        } else {
            $xml = new \SimpleXMLElement('<Station />');
        }

        $xml->addAttribute('name', $this->name);
        $xml->addAttribute('externalId', $this->id);

        return $xml;
    }

    /**
     * {@inheritDoc}
     */
    static public function createFromXml(\SimpleXMLElement $xml, Location $obj = null)
    {
        if (!$obj) {
            $obj = new Station();
        }
        parent::createFromXml($xml, $obj);

        $obj->id = (string) $xml['externalStationNr'];

        return $obj;
    }

    /**
     * {@inheritDoc}
     */
    static public function createFromJson($json, Location $obj = null)
    {
        if (!$obj) {
            $obj = new Station();
        }
        parent::createFromJson($json, $obj);

        $obj->id = $json->extId;

        return $obj;
    }
}
