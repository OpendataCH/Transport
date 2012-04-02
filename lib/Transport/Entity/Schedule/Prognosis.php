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
                if ($xml->Arr->Time) {
                    $obj->arrival = Stop::calculateDateTime((string) $xml->Arr->Time, $date)->format(\DateTime::ISO8601);
                }
            }
        } else {

            if ($xml->Dep) {
                if ($xml->Dep->Platform) {
                    $obj->platform = (string) $xml->Dep->Platform->Text;
                }
                if ($xml->Dep->Time) {
                    $obj->departure = Stop::calculateDateTime((string) $xml->Dep->Time, $date)->format(\DateTime::ISO8601);
                }
            }
        }

        if ($xml->Capacity1st) {
            $obj->capacity1st = (string) $xml->Capacity1st;
        }
        if ($xml->Capacity2nd) {
            $obj->capacity2nd = (string) $xml->Capacity2nd;
        }

        return $obj;
    }
}
