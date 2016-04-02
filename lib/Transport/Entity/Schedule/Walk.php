<?php

namespace Transport\Entity\Schedule;

class Walk
{
    /**
     * @var int
     */
    public $duration;

    /**
     * @param string $time
     */
    static public function parseTime($time)
    {
        if (substr($time, 2, 1) == 'd') {
            return substr($time, 3);
        }
        return $time;
    }

    /**
     * @param \DateTime $date
     */
    static public function createFromXml(\SimpleXMLElement $xml, $date, Walk $obj = null)
    {
        if (!$obj) {
            $obj = new Walk();
        }

        $obj->duration = self::parseTime((string) $xml->Duration->Time);

        return $obj;
    }
}
