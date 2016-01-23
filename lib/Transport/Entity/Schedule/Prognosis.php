<?php

namespace Transport\Entity\Schedule;

class Prognosis
{
    public $platform;
    public $arrival;
    public $departure;
    public $capacity1st;
    public $capacity2nd;

    static public function createFromXml(\SimpleXMLElement $xml, \DateTime $date, $isArrival, Prognosis $obj = null)
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
