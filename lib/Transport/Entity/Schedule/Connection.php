<?php

namespace Transport\Entity\Schedule;

use Transport\Entity;

/**
 * Connection
 */
class Connection
{
    /**
     * @var Transport\Entity\Schedule\Stop
     */
    public $from;

    /**
     * @var Transport\Entity\Schedule\Stop
     */
    public $to;

    /**
     * @var array of Transport\Entity\Schedule\Stop 's
     */
    public $sections;

    static public function createFromXml(\SimpleXMLElement $xml, Connection $obj = null)
    {
        if (!$obj) {
            $obj = new Connection();
        }
        $date = date('Y-m-d', strtotime((string) $xml->Overview->Date));
        $obj->from = Entity\Schedule\Stop::createFromXml($xml->Overview->Departure->BasicStop, $date);
        $obj->to = Entity\Schedule\Stop::createFromXml($xml->Overview->Arrival->BasicStop, $date);

        foreach ($xml->ConSectionList->ConSection as $section) {

            $parts = array();

            if ($section->Journey) {            
                $parts['journey'] = Entity\Schedule\Journey::createFromXml($section->Journey, $date);
            }

            if ($section->Walk) {            
                $parts['walk'] = Entity\Schedule\Walk::createFromXml($section->Walk, $date);
            }

            $parts['departure'] = Entity\Schedule\Stop::createFromXml($section->Departure->BasicStop, $date);
            $parts['arrival'] = Entity\Schedule\Stop::createFromXml($section->Arrival->BasicStop, $date);

            $obj->sections[] = $parts;
        }

        return $obj;
    }
}
