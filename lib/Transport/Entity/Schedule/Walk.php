<?php

namespace Transport\Entity\Schedule;

/**
 * @SWG\Definition()
 */
class Walk
{
    /**
     * @var int
     * @SWG\Property()
     */
    public $duration;

    /**
     * @param string $time
     */
    public static function parseTime($time)
    {
        if (substr($time, 2, 1) == 'd') {
            return substr($time, 3);
        }
        return $time;
    }

    /**
     * @param \DateTime $date
     */
    public static function createFromXml(\SimpleXMLElement $xml, $date, Walk $obj = null)
    {
        if (!$obj) {
            $obj = new Walk();
        }

        $obj->duration = self::parseTime((string) $xml->Duration->Time);

        return $obj;
    }
}
