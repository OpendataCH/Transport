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

        $field = $parentField.'/passList';
        if (ResultLimit::isFieldSet($field)) {
            if ($xml->PassList->BasicStop) {
                foreach ($xml->PassList->BasicStop AS $basicStop) {
                    if ($basicStop->Arr || $basicStop->Dep) {
                        $obj->passList[] = Stop::createFromXml($basicStop, $date, null, $field);
                    }
                }
            }
        }

        return $obj;
    }
}
