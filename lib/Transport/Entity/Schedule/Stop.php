<?php

namespace Transport\Entity\Schedule;

use Transport\Entity;

/**
 * Basic Stop.
 *
 * @SWG\Definition()
 */
class Stop
{
    /**
     * A location object showing this line's stop at the requested station.
     *
     * @var \Transport\Entity\Location\Station
     * @SWG\Property()
     */
    public $station;

    /**
     * The arrival time to the checkpoint (e.g. 14:58:00).
     *
     * @var string
     * @SWG\Property()
     */
    public $arrival;

    /**
     * @var int
     * @SWG\Property()
     */
    public $arrivalTimestamp;

    /**
     * The departure time from the checkpoint, can be null.
     *
     * @var string
     * @SWG\Property()
     */
    public $departure;

    /**
     * @var int
     * @SWG\Property()
     */
    public $departureTimestamp;

    /**
     * @var int
     * @SWG\Property()
     */
    public $delay;

    /**
     * The arrival/departure platform (e.g. 8).
     *
     * @var string
     * @SWG\Property()
     */
    public $platform;

    /**
     * The checkpoint prognosis.
     *
     * @var \Transport\Entity\Schedule\Prognosis
     * @SWG\Property()
     */
    public $prognosis;

    /**
     * @var string
     * @SWG\Property()
     */
    public $realtimeAvailability;

    /**
     * @var \Transport\Entity\Location\Location
     * @SWG\Property()
     */
    public $location;

    public function __construct()
    {
        $this->prognosis = new Prognosis();
    }

    /**
     * Calculates a datetime by parsing the time and date given.
     *
     * @param string    $time          The time to parse, can contain an optional offset prefix (e.g., "02d")
     * @param \DateTime $referenceDate The date
     *
     * @return \DateTime The parsed time in ISO format
     */
    public static function calculateDateTime($time, \DateTime $referenceDate, $stopPrognosis = null)
    {
        // prevent changing the reference
        $date = clone $referenceDate;

        $offset = 0;

        if (substr($time, 2, 1) == 'd') {
            $offset = substr($time, 0, 2);
            $time = substr($time, 3);
        }

        $timeObj = \DateTime::createFromFormat('H:i:s', $time, $date->getTimezone());
        if ($timeObj === false) {
            $timeObj = \DateTime::createFromFormat('H:i', $time, $date->getTimezone());
        }

        $date->setTime($timeObj->format('H'), $timeObj->format('i'), $timeObj->format('s'));

        // check for passed midnight
        $referenceTime = strtotime($referenceDate->format('H:i'));
        $dateTime = strtotime($date->format('H:i'));

        if (isset($stopPrognosis->Dep->Time)) {
            $prognosisTime = strtotime((string) $stopPrognosis->Dep->Time);

            if ($dateTime < $referenceTime && $prognosisTime < $referenceTime && ($dateTime - $prognosisTime) < 0) {

                // we passed midnight
                $offset = 1;
            }
        } elseif (isset($stopPrognosis->Arr->Time)) {
            $prognosisTime = strtotime((string) $stopPrognosis->Arr->Time);

            if ($dateTime < $referenceTime && $prognosisTime < $referenceTime && ($dateTime - $prognosisTime) < 0) {

                // we passed midnight
                $offset = 1;
            }
        } elseif ($dateTime < $referenceTime) {

            // we passed midnight
            $offset = 1;
        }

        $date->add(new \DateInterval('P'.$offset.'D'));

        return $date;
    }

    public static function createFromXml(\SimpleXMLElement $xml, \DateTime $date, Stop $obj = null)
    {
        if (!$obj) {
            $obj = new self();
        }

        $obj->station = Entity\Location\Station::createStationFromXml($xml->Station); // deprecated, use location instead

        foreach ($xml->children() as $location) {
            $location = Entity\LocationFactory::createFromXml($location);
            if ($location) {
                $obj->location = $location;
                break;
            }
        }

        $isArrival = false;
        if ($xml->Arr) {
            $isArrival = true;
            $arrivalDate = self::calculateDateTime((string) $xml->Arr->Time, $date, $xml->StopPrognosis);
            $obj->arrival = $arrivalDate->format(\DateTime::ISO8601);
            $obj->arrivalTimestamp = $arrivalDate->getTimestamp();
            $obj->platform = trim((string) $xml->Arr->Platform->Text);
        }
        if ($xml->Dep) {
            $departureDate = self::calculateDateTime((string) $xml->Dep->Time, $date, $xml->StopPrognosis);
            $obj->departure = $departureDate->format(\DateTime::ISO8601);
            $obj->departureTimestamp = $departureDate->getTimestamp();
            $obj->platform = trim((string) $xml->Dep->Platform->Text);
        }

        $obj->prognosis = Prognosis::createFromXml($xml->StopPrognosis, $date, $isArrival);

        if ($obj->prognosis) {
            if ($obj->prognosis->arrival && $obj->arrival) {
                $obj->delay = (strtotime($obj->prognosis->arrival) - strtotime($obj->arrival)) / 60;
            }
            if ($obj->prognosis->departure && $obj->departure) {
                $obj->delay = (strtotime($obj->prognosis->departure) - strtotime($obj->departure)) / 60;
            }
        }

        if ($xml->StAttrList) {
            foreach ($xml->StAttrList->StAttr as $attr) {
                if ($attr['code'] == 'RA') {
                    $obj->realtimeAvailability = (string) $attr['text'];
                }
            }
        }

        return $obj;
    }

    public static function createFromJson($json, Stop $obj = null)
    {
        if (!$obj) {
            $obj = new self();
        }

        $obj->station = Entity\Location\Station::createStationFromJson($json); // deprecated, use location instead

        $obj->location = Entity\LocationFactory::createFromJson($json);

        if (isset($json->arrival)) {
            $arrivalDate = new \DateTime($json->arrival);
            $obj->arrival = $arrivalDate->format(\DateTime::ISO8601);
            $obj->arrivalTimestamp = $arrivalDate->getTimestamp();
        }
        if (isset($json->arr)) {
            $arrivalDate = new \DateTime($json->arr);
            $obj->arrival = $arrivalDate->format(\DateTime::ISO8601);
            $obj->arrivalTimestamp = $arrivalDate->getTimestamp();
        }
        if (isset($json->departure)) {
            $departureDate = new \DateTime($json->departure);
            $obj->departure = $departureDate->format(\DateTime::ISO8601);
            $obj->departureTimestamp = $departureDate->getTimestamp();
        }
        if (isset($json->dep)) {
            $departureDate = new \DateTime($json->dep);
            $obj->departure = $departureDate->format(\DateTime::ISO8601);
            $obj->departureTimestamp = $departureDate->getTimestamp();
        }
        if (isset($json->time)) {
            $departureDate = new \DateTime($json->time);
            $obj->departure = $departureDate->format(\DateTime::ISO8601);
            $obj->departureTimestamp = $departureDate->getTimestamp();
        }

        $obj->prognosis = Prognosis::createFromJson($json, $obj);

        if ($obj->prognosis) {
            if ($obj->prognosis->arrival && $obj->arrival) {
                $obj->delay = (strtotime($obj->prognosis->arrival) - strtotime($obj->arrival)) / 60;
            }
            if ($obj->prognosis->departure && $obj->departure) {
                $obj->delay = (strtotime($obj->prognosis->departure) - strtotime($obj->departure)) / 60;
            }
        }

        if (isset($json->track)) {
            $obj->platform = $json->track;
        }

        return $obj;
    }
}
