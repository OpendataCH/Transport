<?php

namespace Transport\Entity\Schedule;

use Transport\Entity;

/**
 * Basic Stop
 */
class Stop
{
    public $station;

    public $arrival;
    public $arrivalTimestamp;

    public $departure;
    public $departureTimestamp;

    public $delay;

    public $platform;

    public $prognosis;
    
    public function __construct()
    {
        $this->prognosis = new Prognosis();
    }

    /**
     * Calculates a datetime by parsing the time and date given
     *
     * @param   string		$time		The time to parse, can contain an optional offset prefix (e.g., "02d")
     * @param   \DateTime	$date       The date
     * @return  \DateTime  The parsed time in ISO format
     */
    static public function calculateDateTime($time, \DateTime $date)
    {
        $offset = 0;
        if (substr($time, 2, 1) == 'd') {
            $offset = substr($time, 0, 2);
            $time = substr($time, 3);
        }
        // Prevent changing the reference
        $date = clone $date;
        $date->add(new \DateInterval('P' . $offset . 'D'));
        $timeObj = \DateTime::createFromFormat('H:i:s', $time, $date->getTimezone());
        if ($timeObj === false) {
            $timeObj = \DateTime::createFromFormat('H:i', $time, $date->getTimezone());
        }
        $date->setTime($timeObj->format('H'), $timeObj->format('i'), $timeObj->format('s'));

        return $date;
    }

    static public function createFromXml(\SimpleXMLElement $xml, \DateTime $date, Stop $obj = null)
    {
        if (!$obj) {
            $obj = new Stop();
        }

        $dateTime = null;
        $isArrival = false;

        $obj->station = Entity\Location\Station::createFromXml($xml->Station); // deprecated, use location instead

        foreach ($xml->children() as $location) {

            $location = Entity\LocationFactory::createFromXml($location);
            if ($location) {
                $obj->location = $location;
                break;
            }
        }

        if ($xml->Arr) {
            $isArrival = true;
            $dateTime = self::calculateDateTime((string) $xml->Arr->Time, $date);
            $obj->arrival = $dateTime->format(\DateTime::ISO8601);
            $obj->arrivalTimestamp = $dateTime->getTimestamp();
            $obj->platform = trim((string) $xml->Arr->Platform->Text);
        }
        if ($xml->Dep) {
            $dateTime = self::calculateDateTime((string) $xml->Dep->Time, $date);
            $obj->departure = $dateTime->format(\DateTime::ISO8601);
            $obj->departureTimestamp = $dateTime->getTimestamp();
            $obj->platform = trim((string) $xml->Dep->Platform->Text);
        }
        $obj->prognosis = Prognosis::createFromXml($xml->StopPrognosis, $dateTime, $isArrival);

        if ($obj->prognosis) {
            if ($obj->prognosis->arrival && $obj->arrival) {
                $obj->delay = (strtotime($obj->prognosis->arrival) - strtotime($obj->arrival)) / 60;
            }
            if ($obj->prognosis->departure && $obj->departure) {
                $obj->delay = (strtotime($obj->prognosis->departure) - strtotime($obj->departure)) / 60;
            }
        }

        return $obj;
    }
}
