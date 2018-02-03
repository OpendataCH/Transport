<?php

namespace Transport\Entity\Schedule;

/**
 * @SWG\Definition()
 */
class Walk
{
    /**
     * @var string
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
    public static function createFromXml(\SimpleXMLElement $xml, $date, self $obj = null)
    {
        if (!$obj) {
            $obj = new self();
        }

        $obj->duration = self::parseTime((string) $xml->Duration->Time);

        return $obj;
    }

    public static function createFromJson($json, self $obj = null)
    {
        if (!$obj) {
            $obj = new self();
        }

        if (isset($json->normal_time)) {
            $obj->duration = $json->normal_time;
        }

        return $obj;
    }
}
