<?php

namespace Transport\Entity\Schedule;

use Transport\Entity;
use Transport\ResultLimit;

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
    
    static public function createFromXml(\SimpleXMLElement $xml, \DateTime $date, Section $obj = null, $parentField = '')
    {
        if (!$obj) {
            $obj = new Section();
        }

        $field = $parentField.'/journey';
        if (ResultLimit::isFieldSet($field)) {
            if ($xml->Journey) {
                $obj->journey = Entity\Schedule\Journey::createFromXml($xml->Journey, $date, null, $field);
            }
        }
        $field = $parentField.'/walk';
        if (ResultLimit::isFieldSet($field)) {
            if ($xml->Walk) {
                $obj->walk = Entity\Schedule\Walk::createFromXml($xml->Walk, $date);
            }
        }
        $field = $parentField.'/departure';
        if (ResultLimit::isFieldSet($field)) {
            $obj->departure = Entity\Schedule\Stop::createFromXml($xml->Departure->BasicStop, $date, null, $field);
        }
        $field = $parentField.'/arrival';
        if (ResultLimit::isFieldSet($field)) {
            $obj->arrival = Entity\Schedule\Stop::createFromXml($xml->Arrival->BasicStop, $date, null, $field);
        }

        return $obj;
    }
}
