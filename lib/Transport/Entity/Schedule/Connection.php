<?php

namespace Transport\Entity\Schedule;

use Transport\Entity;

/**
 * Connection
 */
class Connection
{
    public $date;

    /**
     * @var Transport\Entity\Schedule\Stop
     */
    public $from;

    /**
     * @var Transport\Entity\Schedule\Stop
     */
    public $to;

    static public function createFromXml(\SimpleXMLElement $xml, Connection $obj = null)
    {
        if (!$obj) {
            $obj = new Connection();
        }
        $obj->date = date('Y-m-d', strtotime((string) $xml->Overview->Date));
        $obj->from = Entity\Schedule\Stop::createFromXml($xml->Overview->Departure->BasicStop);
        $obj->to = Entity\Schedule\Stop::createFromXml($xml->Overview->Arrival->BasicStop);

        return $obj;
    }
}
