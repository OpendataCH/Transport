<?php

namespace Transport\Entity\Schedule;

use Transport\Entity;

/**
 * Basic Stop
 */
class Stop
{
    public $station;

    public $location;

    public $arrival;
    public $arrivalTimestamp;

    public $departure;
    public $departureTimestamp;

    public $delay;

    public $platform;

    public $prognosis;

    public $realtimeAvailability;

    public function __construct()
    {
        $this->prognosis = new Prognosis();
    }

    /**
     * Calculates a datetime by parsing the time and date given
     *
     * @param   string		$time		The time to parse, can contain an optional offset prefix (e.g., "02d")
     * @param   \DateTime	$referenceDate    The date
     * @return  \DateTime  The parsed time in ISO format
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
        } elseif ($dateTime < $referenceTime) {

            // we passed midnight
            $offset = 1;
        }

        $date->add(new \DateInterval('P' . $offset . 'D'));

        return $date;
    }

    public static function createFromXml(\SimpleXMLElement $xml, \DateTime $date, Stop $obj = null)
    {
        if (!$obj) {
            $obj = new Stop();
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
                if ($attr["code"] == "RA") {
                    $obj->realtimeAvailability = (string) $attr['text'];
                }
            }
        }

        return $obj;
    }
}
