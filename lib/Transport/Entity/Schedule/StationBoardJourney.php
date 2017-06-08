<?php

namespace Transport\Entity\Schedule;

/**
 * Request for a station board journey.
 *
 * @SWG\Definition()
 */
class StationBoardJourney extends Journey
{
    /**
     * @var \Transport\Entity\Schedule\Stop
     * @SWG\Property()
     */
    public $stop;

    /**
     * @param \SimpleXMLElement   $xml
     * @param \DateTime           $date The date that will be assigned to this journey
     * @param StationBoardJourney $obj  An optional existing journey to overwrite
     *
     * @return StationBoardJourney
     */
    public static function createStationBoardFromXml(\SimpleXMLElement $xml, \DateTime $date, StationBoardJourney $obj = null)
    {
        if (!$obj) {
            $obj = new self();
        }

        $stop = Stop::createFromXml($xml->MainStop->BasicStop, $date, null);

        // use resolved date from main stop
        if ($stop->departure) {
            $date = new \DateTime($stop->departure);
        } else {
            $date = new \DateTime($stop->arrival);
        }

        /* @var $obj StationBoardJourney */
        $obj = Journey::createFromXml($xml, $date, $obj);

        $obj->stop = $stop;

        return $obj;
    }

    public static function createFromJson($json, Journey $obj = null)
    {
        if (!$obj) {
            $obj = new self();
        }

        $stop = Stop::createFromJson($json, null);

        /* @var $obj StationBoardJourney */
        $obj = Journey::createFromJson($json, $obj);

        $obj->stop = $stop;

        return $obj;
    }
}
