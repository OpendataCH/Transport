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
     * @var array
     */
    public $serviceDays = array();
    
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
            $obj->duration = (string)$xml->Overview->Duration->Time;
        }
        $field = $parentField.'/transfers';
        if (ResultLimit::isFieldSet($field)) {
            $obj->transfers = (int)$xml->Overview->Transfers;
        }
        $field = $parentField.'/serviceDays';
        if (ResultLimit::isFieldSet($field)) {
            if (isset($xml->Overview->ServiceDays->RegularServiceText)) {
                $obj->serviceDays['regularService'] = (string)$xml->Overview->ServiceDays->RegularServiceText->Text;
            }
            if (isset($xml->Overview->ServiceDays->IrregularServiceText)) {
                $obj->serviceDays['irregularService'] = (string)$xml->Overview->ServiceDays->IrregularServiceText->Text;
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

        if (ResultLimit::isFieldSet($parentField.'/capacity1st') || ResultLimit::isFieldSet($parentField.'/capacity2nd')) {
            $capacities1st = array();
            $capacities2nd = array();
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
        if (ResultLimit::isFieldSet($field)) {
            $obj->capacity1st = max($capacities1st);   
        }
        $field = $parentField.'/capacity2nd';
        if (ResultLimit::isFieldSet($field)) {
            $obj->capacity2nd = max($capacities2nd);   
        }

        $field = $parentField.'/sections';
        if (ResultLimit::isFieldSet($field)) {
            $parentField = $field;
            foreach ($xml->ConSectionList->ConSection as $section) {
    
                $parts = array();
                
                $field = $parentField.'/journey';
                if (ResultLimit::isFieldSet($field)) {
                    if ($section->Journey) {
                        $parts['journey'] = Entity\Schedule\Journey::createFromXml($section->Journey, $date, null, $field);
                    }
                }
                $field = $parentField.'/walk';
                if (ResultLimit::isFieldSet($field)) {
                    if ($section->Walk) {
                        $parts['walk'] = Entity\Schedule\Walk::createFromXml($section->Walk, $date);
                    }
                }
                $field = $parentField.'/departure';
                if (ResultLimit::isFieldSet($field)) {
                    $parts['departure'] = Entity\Schedule\Stop::createFromXml($section->Departure->BasicStop, $date, null, $field);
                }
                $field = $parentField.'/departure';
                if (ResultLimit::isFieldSet($field)) {
                    $parts['arrival'] = Entity\Schedule\Stop::createFromXml($section->Arrival->BasicStop, $date, null, $field);
                }

                $obj->sections[] = $parts;
            }
        } 
        return $obj;
    }
}