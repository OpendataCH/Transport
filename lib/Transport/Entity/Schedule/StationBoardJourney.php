<?php

namespace Transport\Entity\Schedule;

use Transport\ResultLimit;

/**
 * Request for a station board journey
 */
class StationBoardJourney extends Journey
{
    /**
     * @var Transport\Entity\Schedule\Stop
     */
    public $stop;

    /**
     * @param   \SimpleXMLElement   $xml
     * @param   string              $date   The date that will be assigned to this journey
     * @param   Journey             $obj    An optional existing journey to overwrite
     * @return  Journey
     */
    static public function createFromXml(\SimpleXMLElement $xml, \DateTime $date, Journey $obj = null, $parentField = '')
    {
        if (!$obj) {
            $obj = new StationBoardJourney();
        }

        $obj = Journey::createFromXml($xml, $date, $obj);

        $field = $parentField.'/stop';
        if (ResultLimit::isFieldSet($field)) {
            $obj->stop = Stop::createFromXml($xml->MainStop->BasicStop, $date, null, $field);
        }

        return $obj;
    }
}
