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