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
     * 00d21:06:00 to 21:06:00
     */
    static public function parseTime($time)
    {
        if (substr($time, 0, 3) == '00d') {
            return substr($time, 3);
        }
        return $time;
    }

    static public function createFromXml(\SimpleXMLElement $xml, Stop $obj = null)
    {
        if (!$obj) {
            $obj = new Stop();
        }

        $obj->station = Entity\Location\Station::createFromXml($xml->Station);
        if ($xml->Arr) {
            $obj->arrival = self::parseTime((string) $xml->Arr->Time);
            $obj->platform = trim((string) $xml->Arr->Platform->Text);
        }
        if ($xml->Dep) {
            $obj->departure = self::parseTime((string) $xml->Dep->Time);
            $obj->platform = trim((string) $xml->Dep->Platform->Text);
        }
        $obj->prognosis = Prognosis::createFromXml($xml->StopPrognosis);

        return $obj;
    }
}
