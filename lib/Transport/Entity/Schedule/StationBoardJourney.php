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
    public $number;

    /**
     * @var string
     */
    public $operator;

    /**
     * @var string
     */
    public $to;

    /**
     * @param   \SimpleXMLElement   $xml
     * @param   string              $date   The date that will be assigned to this journey
     * @param   StationBoardJourney $obj    An optional existing journey to overwrite
     * @return  StationBoardJourney
     */
    static public function createFromXml(\SimpleXMLElement $xml, $date, StationBoardJourney $obj = null)
    {
        if (!$obj) {
            $obj = new StationBoardJourney();
        }

        $obj->stop = Stop::createFromXml($xml->MainStop->BasicStop, $date);

        // TODO: get attributes
        foreach ($xml->JourneyAttributeList->JourneyAttribute AS $journeyAttribute) {
        
            switch ($journeyAttribute->Attribute['type']) {
                case 'NAME':
                    $obj->name = (string) $journeyAttribute->Attribute->AttributeVariant->Text;
                    break;
                case 'CATEGORY':
                    $obj->category = (string) $journeyAttribute->Attribute->AttributeVariant->Text;
                    break;
                case 'NUMBER':
                    $obj->number = (string) $journeyAttribute->Attribute->AttributeVariant->Text;
                    break;
                case 'OPERATOR':
                    $obj->operator = (string) $journeyAttribute->Attribute->AttributeVariant->Text;
                    break;
                case 'DIRECTION':
                    $obj->to = (string) $journeyAttribute->Attribute->AttributeVariant->Text;
                    break;
            }
        }

        return $obj;
    }
}
