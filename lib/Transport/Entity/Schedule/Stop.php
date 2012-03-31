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
    public $departure;

    public $platform;

    public $prognosis;

    public function __construct() {
        $this->prognosis = new Prognosis(); 
    }

    /**
     * Calculates a datetime by parsing the time and date given
     *
     * @param   string  $time       The time to parse, can contain an optional offset prefix (e.g., "02d")
     * @param   string  $date       The date
     * @return  string  The parsed time in ISO format
     */
    static public function calculateDateTime($time, $date)
    {
        if (substr($time, 2, 1) == 'd') {
            $offset = substr($time, 0, 2);
            $time = substr($time, 3);
            $date = date('Y-m-d', strtotime("$date +$offset days"));
        }

        return date('c', strtotime("$date $time"));
    }

    static public function parseTime($time)
    {
        if (substr($time, 2, 1) == 'd') {
            return substr($time, 3);
        }
        return $time;
    }

    static public function createFromXml(\SimpleXMLElement $xml, $date, Stop $obj = null)
    {
        if (!$obj) {
            $obj = new Stop();
        }

        $obj->station = Entity\Location\Station::createFromXml($xml->Station);
        if ($xml->Arr) {
            $obj->arrival = self::calculateDateTime((string) $xml->Arr->Time, $date);
            $obj->platform = trim((string) $xml->Arr->Platform->Text);
        }
        if ($xml->Dep) {
            $obj->departure = self::calculateDateTime((string) $xml->Dep->Time, $date);
            $obj->platform = trim((string) $xml->Dep->Platform->Text);
        }
        $obj->prognosis = Prognosis::createFromXml($xml->StopPrognosis);

        return $obj;
    }
}
