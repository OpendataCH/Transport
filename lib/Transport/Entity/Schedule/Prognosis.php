<?php

namespace Transport\Entity\Schedule;

class Prognosis
{
    public $platform;
    public $time;
    public $capacity1st;
    public $capacity2nd;

    static public function createFromXml(\SimpleXMLElement $xml, Prognosis $obj = null)
    {
        if (!$obj) {
            $obj = new Prognosis();
        }

        if ($xml->Arr->Platform) {
            $obj->platform = Stop::parseTime((string) $xml->Arr->Platform->Text);
        }
        if ($xml->Arr->Time) {
            $obj->time = (string) $xml->Arr->Time;
        }
        if ($xml->Dep->Platform) {
            $obj->platform = (string) $xml->Dep->Platform->Text;
        }
        if ($xml->Dep->Time) {
            $obj->time = Stop::parseTime((string) $xml->Dep->Time);
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
