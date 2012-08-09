<?php

namespace Transport\Entity\Schedule;

use Transport\Entity;

class Section
{
    /**
     * @var Entity\Schedule\Journey
     */
    public $journey;

    /**
     * @var Entity\Schedule\Walk
     */
    public $walk;

    /**
     * @var Entity\Schedule\Stop
     */
    public $departure;

    /**
     * @var Entity\Schedule\Stop
     */
    public $arrival;
    
    static public function createFromXml(\SimpleXMLElement $xml, \DateTime $date, Section $obj = null)
    {
        if (!$obj) {
            $obj = new Section();
        }

        if ($xml->Journey) {
            $obj->journey = Entity\Schedule\Journey::createFromXml($xml->Journey, $date, null);
        }

        if ($xml->Walk) {
            $obj->walk = Entity\Schedule\Walk::createFromXml($xml->Walk, $date);
        }

        $obj->departure = Entity\Schedule\Stop::createFromXml($xml->Departure->BasicStop, $date, null);
        $obj->arrival = Entity\Schedule\Stop::createFromXml($xml->Arrival->BasicStop, $date, null);

        return $obj;
    }
}
