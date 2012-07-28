<?php

namespace Transport\Entity\Schedule;

use Transport\ResultLimit;

class Journey
{

    /**
     * @var string
     */
    public $name;

    /**
     * @var string
     */
    public $category;

    /**
     * @var string
     */
    public $number;

    /**
     * @var string
     */
    public $operator;

    /**
     * @var string
     */
    public $to;

    /**
     * @var array
     */
    public $passList = array();

    /**
     * @var int
     */
    public $capacity1st = null;

    /**
     * @var int
     */
    public $capacity2nd = null;

    static public function createFromXml(\SimpleXMLElement $xml, \DateTime $date, Journey $obj = null, $parentField = '')
    {
        if (!$obj) {
            $obj = new Journey();
        }

        // TODO: get attributes
        if ($xml->JourneyAttributeList) {
            foreach ($xml->JourneyAttributeList->JourneyAttribute AS $journeyAttribute) {
            
                switch ($journeyAttribute->Attribute['type']) {
                    case 'NAME':
                        $obj->name = (string) $journeyAttribute->Attribute->AttributeVariant->Text;
                        break;
                    case 'CATEGORY':
                        $obj->category = (string) $journeyAttribute->Attribute->AttributeVariant->Text;
                        break;
                    case 'INTERNALCATEGORY':
                        $obj->subcategory = (string) $journeyAttribute->Attribute->AttributeVariant->Text;
                        break;
                    case 'NUMBER':
                        $obj->number = (string) $journeyAttribute->Attribute->AttributeVariant->Text;
                        break;
                    case 'OPERATOR':
                        $obj->operator = (string) $journeyAttribute->Attribute->AttributeVariant->Text;
                        break;
                    case 'DIRECTION':
                        $obj->to = (string) $journeyAttribute->Attribute->AttributeVariant->Text;
                        break;
                }
            }
        }

        $capacities1st = array();
        $capacities2nd = array();

        $field = $parentField.'/passList';
        if (ResultLimit::isFieldSet($field)) {
            if ($xml->PassList->BasicStop) {
                foreach ($xml->PassList->BasicStop AS $basicStop) {
                    if ($basicStop->Arr || $basicStop->Dep) {
                        $stop = Stop::createFromXml($basicStop, $date, null, $field);
                        if ($stop->prognosis->capacity1st) {
                            $capacities1st[] = (int) $stop->prognosis->capacity1st;
                        }
                        if ($stop->prognosis->capacity2nd) {
                            $capacities2nd[] = (int) $stop->prognosis->capacity2nd;
                        }
                        $obj->passList[] = $stop;
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

        return $obj;
    }
}
