<?php

namespace Transport\Entity\Location;

/**
 * Represents a Poi we received as response.
 *
 * <Poi name="Ittigen, Bahnhof" score="100" type="WGS84" x="7478189" y="46976494" />
 *
 * @SWG\Definition()
 */
class Poi extends Location
{
    /**
     * {@inheritdoc}
     */
    public function toXml(\SimpleXMLElement $parent = null)
    {
        if (null !== $parent) {
            $xml = $parent->addChild('Poi');
        } else {
            $xml = new \SimpleXMLElement('<Poi />');
        }

        $xml->addAttribute('name', $this->name);

        return $xml;
    }

    /**
     * {@inheritdoc}
     */
    public static function createFromXml(\SimpleXMLElement $xml, Location $obj = null)
    {
        if (!$obj) {
            $obj = new self();
        }

        return parent::createFromXml($xml, $obj);
    }
}
