<?php

namespace Transport\Entity\Schedule;

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
     * @param   \DateTime           $date   The date that will be assigned to this journey
     * @param   Journey             $obj    An optional existing journey to overwrite
     * @return  Journey
     */
    public static function createFromXml(\SimpleXMLElement $xml, \DateTime $date, Journey $obj = null)
    {
        if (!$obj) {
            $obj = new StationBoardJourney();
        }

        $stop = Stop::createFromXml($xml->MainStop->BasicStop, $date, null);

        // use resolved date from main stop
        $date = new \DateTime($stop->departure);

        $obj = Journey::createFromXml($xml, $date, $obj);

        $obj->stop = $stop;

        return $obj;
    }
}
