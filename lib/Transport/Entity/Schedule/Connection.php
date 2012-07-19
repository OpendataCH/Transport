<?php

namespace Transport\Entity\Schedule;

use Transport\Entity;
use Transport\ResultLimit;

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
     * @var String
     */
    public $duration;
    
    /**
     * @var int
     */
    public $transfers;

    /**
     * @var Transport\EntitySchedule\Service
     */
    public $service;

    /**
     * @var array
     */
    public $products = array();
    
    /**
     * @var int
     */
    public $capacity1st = null;
    
    /**
     * @var int
     */
    public $capacity2nd = null;

    /**
     * @var array of Transport\Entity\Schedule\Stop 's
     */
    public $sections;

    static public function createFromXml(\SimpleXMLElement $xml, Connection $obj = null, $parentField = '')
    {
        if (!$obj) {
            $obj = new Connection();
        }
        $date = \DateTime::createFromFormat('Ymd', (string) $xml->Overview->Date, new \DateTimeZone('Europe/Zurich'));
        $date->setTimezone(new \DateTimeZone('Europe/Zurich'));
        $date->setTime(0, 0, 0);  
        
        $field = $parentField.'/from';
        if (ResultLimit::isFieldSet($field)) {
            $obj->from = Entity\Schedule\Stop::createFromXml($xml->Overview->Departure->BasicStop, $date, null, $field);
        }
        $field = $parentField.'/to';
        if (ResultLimit::isFieldSet($field)) {
            $obj->to = Entity\Schedule\Stop::createFromXml($xml->Overview->Arrival->BasicStop, $date, null, $field);
        }
        $field = $parentField.'/duration';
        if (ResultLimit::isFieldSet($field)) {
            $obj->duration = (string) $xml->Overview->Duration->Time;
        }
        $field = $parentField.'/transfers';
        if (ResultLimit::isFieldSet($field)) {
            $obj->transfers = (int) $xml->Overview->Transfers;
        }
        $field = $parentField.'/service';
        if (ResultLimit::isFieldSet($field)) {
        	$obj->service = new Entity\Schedule\Service();
            if (isset($xml->Overview->ServiceDays->RegularServiceText)) {
                $obj->service->regular = (string) $xml->Overview->ServiceDays->RegularServiceText->Text;
            }
            if (isset($xml->Overview->ServiceDays->IrregularServiceText)) {
                $obj->service->irregular = (string) $xml->Overview->ServiceDays->IrregularServiceText->Text;
            }
        }
        $field = $parentField.'/products';
        if (ResultLimit::isFieldSet($field)) {
            if (isset($xml->Overview->Products->Product)) {
                foreach ($xml->Overview->Products->Product as $product) {
                    $obj->products[] = trim((string)$product['cat']);
                }
            }
        }

	    $capacities1st = array();
	    $capacities2nd = array();
        if (ResultLimit::isFieldSet($parentField.'/capacity1st') || ResultLimit::isFieldSet($parentField.'/capacity2nd')) {
            foreach ($xml->ConSectionList->ConSection as $section) {
                if ($section->Journey) {
                    if ($section->Journey->PassList->BasicStop) {
                        foreach ($section->Journey->PassList->BasicStop as $stop) {
                            if (isset($stop->StopPrognosis->Capacity1st)) {
                                $capacities1st[] = (int)$stop->StopPrognosis->Capacity1st;
                            }
                            if (isset($stop->StopPrognosis->Capacity2nd)) {
                                $capacities2nd[] = (int)$stop->StopPrognosis->Capacity2nd;
                            }
                        }
                    }
                }
            }
        }
        $field = $parentField.'/capacity1st';
        if (ResultLimit::isFieldSet($field) && count($capacities1st) > 0) {
            $obj->capacity1st = max($capacities1st);   
        }
        $field = $parentField.'/capacity2nd';
        if (ResultLimit::isFieldSet($field) && count($capacities2nd) > 0) {
            $obj->capacity2nd = max($capacities2nd);   
        }

        $field = $parentField.'/sections';
        if (ResultLimit::isFieldSet($field)) {
            $parentField = $field;
            foreach ($xml->ConSectionList->ConSection as $section) {

                $obj->sections[] = Entity\Schedule\Section::createFromXml($section, $date, null, $parentField);
            }
        } 
        return $obj;
    }
}