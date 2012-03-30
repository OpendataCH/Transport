<?php

namespace Transport\Entity\Schedule;

/**
 * Request for a station board journey
 */
class StationBoardJourney
{
    /**
     * @var Transport\Entity\Schedule\Stop
     */
    public $stop;

    /**
     * @var string
     */
    public $name;

    /**
     * @var string
     */
    public $category;

    /**
     * @var string
     */
    public $operator;

    /**
     * @var string
     */
    public $to;

    static public function createFromXml(\SimpleXMLElement $xml, StationBoardJourney $obj = null)
    {
        if (!$obj) {
            $obj = new StationBoardJourney();
        }

        $obj->stop = Stop::createFromXml($xml->MainStop->BasicStop);

        // TODO: get attributes
        foreach ($xml->JourneyAttributeList->JourneyAttribute AS $journeyAttribute) {
        
            switch ($journeyAttribute->Attribute['type']) {
                case 'NAME':
                    $obj->name = (string) $journeyAttribute->Attribute->AttributeVariant->Text;
                    break;
                case 'CATEGORY':
                    $obj->category = (string) $journeyAttribute->Attribute->AttributeVariant->Text;
                    break;
                case 'OPERATOR':
                    $obj->operator = (string) $journeyAttribute->Attribute->AttributeVariant->Text;
                    break;
                case 'DIRECTION':
                    $obj->to = utf8_decode((string) $journeyAttribute->Attribute->AttributeVariant->Text);
                    break;
            }
        }

        return $obj;
    }
}
