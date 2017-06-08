<?php

namespace Transport\Entity\Schedule;

use Transport\Entity;

/**
 * A connection represents a possible journey between two locations.
 *
 * @SWG\Definition()
 */
class Connection
{
    /**
     * The departure checkpoint of the connection.
     *
     * @var \Transport\Entity\Schedule\Stop
     * @SWG\Property()
     */
    public $from;

    /**
     * The arrival checkpoint of the connection.
     *
     * @var \Transport\Entity\Schedule\Stop
     * @SWG\Property()
     */
    public $to;

    /**
     * Duration of the journey (e.g. 00d00:43:00).
     *
     * @var string
     * @SWG\Property()
     */
    public $duration;

    /**
     * Service information about how regular the connection operates.
     *
     * @var int
     * @SWG\Property()
     */
    public $transfers;

    /**
     * List of transport products (e.g. IR, S9).
     *
     * @var \Transport\Entity\Schedule\Service
     * @SWG\Property()
     */
    public $service;

    /**
     * @var string[]
     * @SWG\Property()
     */
    public $products = [];

    /**
     * The maximum estimated occupation load of 1st class coaches (e.g. 1).
     *
     * @var int
     * @SWG\Property()
     */
    public $capacity1st = null;

    /**
     * The maximum estimated occupation load of 2nd class coaches (e.g. 2).
     *
     * @var int
     * @SWG\Property()
     */
    public $capacity2nd = null;

    /**
     * A list of sections.
     *
     * @var \Transport\Entity\Schedule\Section[]
     * @SWG\Property()
     */
    public $sections;

    public static function createFromXml(\SimpleXMLElement $xml, Connection $obj = null)
    {
        if (!$obj) {
            $obj = new self();
        }
        $date = \DateTime::createFromFormat('Ymd', (string) $xml->Overview->Date, new \DateTimeZone('Europe/Zurich'));
        $date->setTimezone(new \DateTimeZone('Europe/Zurich'));
        $date->setTime(0, 0, 0);

        $obj->from = Entity\Schedule\Stop::createFromXml($xml->Overview->Departure->BasicStop, $date, null);
        $obj->to = Entity\Schedule\Stop::createFromXml($xml->Overview->Arrival->BasicStop, $date, null);

        $obj->duration = (string) $xml->Overview->Duration->Time;
        $obj->transfers = (int) $xml->Overview->Transfers;

        $obj->service = new Entity\Schedule\Service();
        if (isset($xml->Overview->ServiceDays->RegularServiceText)) {
            $obj->service->regular = (string) $xml->Overview->ServiceDays->RegularServiceText->Text;
        }
        if (isset($xml->Overview->ServiceDays->IrregularServiceText)) {
            $obj->service->irregular = (string) $xml->Overview->ServiceDays->IrregularServiceText->Text;
        }

        if (isset($xml->Overview->Products->Product)) {
            foreach ($xml->Overview->Products->Product as $product) {
                $obj->products[] = trim((string) $product['cat']);
            }
        }

        $capacities1st = [];
        $capacities2nd = [];
        foreach ($xml->ConSectionList->ConSection as $section) {
            if ($section->Journey) {
                if ($section->Journey->PassList->BasicStop) {
                    foreach ($section->Journey->PassList->BasicStop as $stop) {
                        if (isset($stop->StopPrognosis->Capacity1st)) {
                            $capacities1st[] = (int) $stop->StopPrognosis->Capacity1st;
                        }
                        if (isset($stop->StopPrognosis->Capacity2nd)) {
                            $capacities2nd[] = (int) $stop->StopPrognosis->Capacity2nd;
                        }
                    }
                }
            }
        }

        if (count($capacities1st) > 0) {
            $obj->capacity1st = max($capacities1st);
        }
        if (count($capacities2nd) > 0) {
            $obj->capacity2nd = max($capacities2nd);
        }

        foreach ($xml->ConSectionList->ConSection as $section) {
            $obj->sections[] = Entity\Schedule\Section::createFromXml($section, $date, null);
        }

        return $obj;
    }

    public static function createFromJson($json, Connection $obj = null)
    {
        if (!$obj) {
            $obj = new self();
        }

        $obj->from = Entity\Schedule\Stop::createFromJson($json->legs[0], null);
        $obj->to = Entity\Schedule\Stop::createFromJson($json->legs[count($json->legs) - 1], null);

        if (!$obj->to->platform && isset($json->legs[count($json->legs) - 2]->track)) {
            $obj->to->platform = $json->legs[count($json->legs) - 2]->track;
        }

        $obj->duration = gmdate('0z\dH:i:s', $json->duration);
        $obj->transfers = count($json->legs) - 1;

        if (isset($json->legs)) {
            foreach ($json->legs as $leg) {
                if (isset($leg->line)) {
                    $obj->products[] = $leg->line;
                }

                if (isset($leg->type)) {
                    $obj->sections[] = Entity\Schedule\Section::createFromJson($leg, null);
                }
            }
        }

        return $obj;
    }
}
