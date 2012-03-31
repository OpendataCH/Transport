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
     * 01d21:06:00 to 21:06:00
     * @param   string  $time           The time to parse
     * @return  string  The parsed time
     */
    static public function parseTime($time)
    {
        if (substr($time, 2, 1) == 'd') {
            return substr($time, 3);
        }
        return $time;
    }

    /**
     * Looks at the $time for an offset and adjusts the given $date
     *
     * @param   string  $time           The time to extract the offset from
     * @param   string  $date       The base date in case an offset was detected
     * @return  string  The adjusted date as YYYY-MM-DD
     */
    static public function parseDate($time, $date)
    {
        if (substr($time, 2, 1) == 'd') { // day offset
            $days = (int)substr($time, 0, 2);
            $time = substr($time, 3);
            $date = date('Y-m-d', strtotime("$date +$days days"));
        }
        return $date;

    }

    static public function createFromXml(\SimpleXMLElement $xml, $date = null, Stop $obj = null)
    {
        if (!$obj) {
            $obj = new Stop();
        }

        $obj->station = Entity\Location\Station::createFromXml($xml->Station);
        if ($xml->Arr) {
            if ($date) {
                $obj->date = self::parseDate((string) $xml->Arr->Time, $date);
            }
            $obj->arrival = self::parseTime((string) $xml->Arr->Time, $date);
            $obj->platform = trim((string) $xml->Arr->Platform->Text);
        }
        if ($xml->Dep) {
            if ($date) {
                $obj->date = self::parseDate((string) $xml->Arr->Time, $date);
            }
            $obj->departure = self::parseTime((string) $xml->Dep->Time, $date);
            $obj->platform = trim((string) $xml->Dep->Platform->Text);
        }
        $obj->prognosis = Prognosis::createFromXml($xml->StopPrognosis);

        return $obj;
    }
}
