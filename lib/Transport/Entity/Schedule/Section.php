<?php

namespace Transport\Entity\Schedule;

use Transport\Entity;

/**
 * A connection consists of one or multiple sections.
 *
 * @SWG\Definition()
 */
class Section
{
    /**
     * A journey, the transportation used by this section, can be null.
     *
     * @var Entity\Schedule\Journey
     * @SWG\Property()
     */
    public $journey;

    /**
     * Information about walking distance, if available, can be null.
     *
     * @var Entity\Schedule\Walk
     * @SWG\Property()
     */
    public $walk;

    /**
     * The departure checkpoint of the connection.
     *
     * @var Entity\Schedule\Stop
     * @SWG\Property()
     */
    public $departure;

    /**
     * The arrival checkpoint of the connection.
     *
     * @var Entity\Schedule\Stop
     * @SWG\Property()
     */
    public $arrival;

    public static function createFromXml(\SimpleXMLElement $xml, \DateTime $date, self $obj = null)
    {
        if (!$obj) {
            $obj = new self();
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

    public static function createFromJson($json, self $obj = null)
    {
        if (!$obj) {
            $obj = new self();
        }

        if (isset($json->tripid)) {
            $obj->journey = Entity\Schedule\Journey::createFromJson($json, null);
        }

        if ((isset($json->type) && $json->type === 'walk')) {
            $obj->walk = Entity\Schedule\Walk::createFromJson($json);
        }

        $obj->departure = Entity\Schedule\Stop::createFromJson($json, null);
        if (isset($json->exit)) {
            $obj->arrival = Entity\Schedule\Stop::createFromJson($json->exit, null);
        }

        return $obj;
    }
}
