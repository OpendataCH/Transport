<?php

namespace Transport\Entity\Schedule;

class Walk
{
    /**
     * @var int
     */
    public $duration;

    static public function createFromXml(\SimpleXMLElement $xml, $date, Walk $obj = null)
    {
        if (!$obj) {
            $obj = new Walk();
        }

        $obj->duration = Stop::parseTime((string) $xml->Duration->Time);

        return $obj;
    }
}
