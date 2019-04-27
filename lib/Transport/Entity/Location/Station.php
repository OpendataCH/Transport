<?php

namespace Transport\Entity\Location;

/**
 * Represents a station we received as response.
 *
 * <Station name="Bern Felsenau" score="81" externalId="008508051#95" externalStationNr="008508051" type="WGS84" x="7444245" y="46968493"/>
 *
 * @SWG\Definition()
 */
class Station extends Location
{
    /**
     * Mapping between search.ch icon class and
     * more generic icon types
     */
    private static $icons = [
        'sl-icon-type-train'        => 'train',
        'sl-icon-type-tram'         => 'tram',
        'sl-icon-type-funicular'    => 'cableway',
        'sl-icon-type-bus'          => 'bus',
        'sl-icon-type-ship'         => 'ship'
    ];

    /**
     * The ID of the station.
     *
     * @var string
     * @SWG\Property()
     */
    public $id;

    /**
     * @param string $id
     */
    public function __construct($id = null)
    {
        $this->id = $id;
    }

    /**
     * {@inheritdoc}
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

    public static function createStationFromXml(\SimpleXMLElement $xml, self $obj = null)
    {
        if (!$obj) {
            $obj = new self();
        }
        Location::createFromXml($xml, $obj);

        $obj->id = (string) $xml['externalStationNr'];

        return $obj;
    }

    /**
     * @param object $json The item JSON
     */
    public static function createStationFromJson($json, self $obj = null)
    {
        if (!$obj) {
            $obj = new self();
        }
        Location::createFromJson($json, $obj);

        if (isset($json->id)) {
            $obj->id = $json->id;
        }

        if (isset($json->stopid)) {
            $obj->id = $json->stopid;
        }

        if (isset($json->terminal->id)) {
            $obj->id = $json->terminal->id;
        }

        if (isset($json->iconclass)) {
            $obj->icon = array_key_exists($json->iconclass, self::$icons) ? self::$icons[$json->iconclass] : null;
        }

        return $obj;
    }
}
