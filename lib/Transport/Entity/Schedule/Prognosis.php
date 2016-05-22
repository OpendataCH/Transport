<?php

namespace Transport\Entity\Schedule;

/**
 * A prognosis contains "realtime" informations on the status of a connection checkpoint.
 *
 * @SWG\Definition()
 */
class Prognosis
{
    /**
     * The estimated arrival/departure platform (e.g. 8)
     * @var string
     * @SWG\Property()
     */
    public $platform;

    /**
     * The departure time prognosis to the checkpoint, date format: [ISO 8601](http://en.wikipedia.org/wiki/ISO_8601) (e.g. 2012-03-31T08:58:00+02:00)
     * @var string
     * @SWG\Property()
     */
    public $arrival;

    /**
     * The arrival time prognosis to the checkpoint, date format: [ISO 8601](http://en.wikipedia.org/wiki/ISO_8601) (e.g. 2012-03-31T09:35:00+02:00)
     * @var string
     * @SWG\Property()
     */
    public $departure;

    /**
     * The estimated occupation load of 1st class coaches (e.g. 1)
     * @var int
     * @SWG\Property()
     */
    public $capacity1st;

    /**
     * The estimated occupation load of 2nd class coaches (e.g. 2)
     * @var int
     * @SWG\Property()
     */
    public $capacity2nd;

    public static function createFromXml(\SimpleXMLElement $xml, \DateTime $date, $isArrival, Prognosis $obj = null)
    {
        if (!$obj) {
            $obj = new Prognosis();
        }

        if ($isArrival) {
            if ($xml->Arr) {
                if ($xml->Arr->Platform) {
                    $obj->platform = (string) $xml->Arr->Platform->Text;
                }
            }
        } else {
            if ($xml->Dep) {
                if ($xml->Dep->Platform) {
                    $obj->platform = (string) $xml->Dep->Platform->Text;
                }
            }
        }

        if ($xml->Arr) {
            if ($xml->Arr->Time) {
                $arrivalDate = Stop::calculateDateTime((string) $xml->Arr->Time, $date);
                $obj->arrival = $arrivalDate->format(\DateTime::ISO8601);
            }
        }

        if ($xml->Dep) {
            if ($xml->Dep->Time) {
                $departureDate = Stop::calculateDateTime((string) $xml->Dep->Time, $date);
                $obj->departure = $departureDate->format(\DateTime::ISO8601);
            }
        }

        if ($xml->Capacity1st) {
            $obj->capacity1st = (int) $xml->Capacity1st;
        }
        if ($xml->Capacity2nd) {
            $obj->capacity2nd = (int) $xml->Capacity2nd;
        }

        return $obj;
    }
}
