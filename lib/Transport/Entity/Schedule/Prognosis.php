<?php

namespace Transport\Entity\Schedule;

class Prognosis
{
    public $platform;
    public $arrival;
    public $departure;
    public $capacity1st;
    public $capacity2nd;
    public $realtimeProb = 0; //adds a probability for being a realtime info. 0 = no, 25 = maybe not, 75 = maybe, 100 = certainly
    
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
                $obj->arrival = Stop::calculateDateTime((string) $xml->Arr->Time, $date)->format(\DateTime::ISO8601);
            }
        }

        if ($xml->Dep) {
            if ($xml->Dep->Time) {
                $obj->departure = Stop::calculateDateTime((string) $xml->Dep->Time, $date)->format(\DateTime::ISO8601);
            }
        }

        if ($xml->Capacity1st) {
            $obj->capacity1st = (int) $xml->Capacity1st;
        }
        if ($xml->Capacity2nd) {
            $obj->capacity2nd = (int) $xml->Capacity2nd;
        }
        if ($xml->Status) {
            $obj->realtimeProb = 25;
        }

        return $obj;
    }
}
