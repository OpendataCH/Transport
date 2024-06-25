<?php

namespace Transport\Entity\Schedule;

/**
 * The actual transportation of a section, e.g. a bus or a train between two stations.
 *
 * @SWG\Definition()
 */
class Journey
{
    /**
     * The name of the connection (e.g. 019351).
     *
     * @var string
     * @SWG\Property()
     */
    public $name;

    /**
     * The type of connection this is (e.g. S).
     *
     * @var string
     * @SWG\Property()
     */
    public $category;

    /**
     * @var string
     * @SWG\Property()
     */
    public $subcategory;

    /**
     * An internal category code, indicates the type of the public transport vehicle. Possible values are 0, 1, 2, 3, 5, 8: train; 4: ship; 6: bus; 7: cable car (aerial, big); 9: tram.
     *
     * @var int
     * @SWG\Property()
     */
    public $categoryCode;

    /**
     * The number of the connection's line (e.g. 13).
     *
     * @var string
     * @SWG\Property()
     */
    public $number;

    /**
     * The operator of the connection's line (e.g. BBA).
     *
     * @var string
     * @SWG\Property()
     */
    public $operator;

    /**
     * The final destination of this line (e.g. Aarau Rohr, Unterdorf).
     *
     * @var string
     * @SWG\Property()
     */
    public $to;

    /**
     * Checkpoints the train passed on the journey.
     *
     * @var \Transport\Entity\Schedule\Stop[]
     * @SWG\Property()
     */
    public $passList = [];

    /**
     * The maximum estimated occupation load of 1st class coaches (e.g. 1).
     *
     * @var int
     * @SWG\Property()
     */
    public $capacity1st = null;

    /**
     * The maximum estimated occupation load of 2nd class coaches (e.g. 2).
     *
     * @var int
     * @SWG\Property()
     */
    public $capacity2nd = null;

    public static function createFromXml(\SimpleXMLElement $xml, \DateTime $date, $obj = null)
    {
        if (!$obj) {
            $obj = new self();
        }

        // TODO: get attributes
        if ($xml->JourneyAttributeList) {
            foreach ($xml->JourneyAttributeList->JourneyAttribute as $journeyAttribute) {
                switch ($journeyAttribute->Attribute['type']) {
                    case 'NAME':
                        $obj->name = (string) $journeyAttribute->Attribute->AttributeVariant->Text;
                        break;
                    case 'CATEGORY':
                        $obj->category = (string) $journeyAttribute->Attribute->AttributeVariant->Text;
                        $obj->categoryCode = (int) $journeyAttribute->Attribute['code'];
                        break;
                    case 'INTERNALCATEGORY':
                        $obj->subcategory = (string) $journeyAttribute->Attribute->AttributeVariant->Text;
                        break;
                    case 'LINE':
                        $line = (string) $journeyAttribute->Attribute->AttributeVariant->Text;
                        if ($line && !$obj->number) {
                            $obj->number = $line;
                        }
                        break;
                    case 'NUMBER':
                        $number = (string) $journeyAttribute->Attribute->AttributeVariant->Text;
                        if ($number && !$obj->number) {
                            $obj->number = $number;
                        }
                        break;
                    case 'OPERATOR':
                        foreach ($journeyAttribute->Attribute->AttributeVariant as $journeyAttributeVariant) {
                            if ($journeyAttributeVariant['type'] == 'NORMAL') {
                                $obj->operator = (string) $journeyAttributeVariant->Text;
                            }
                        }
                        break;
                    case 'DIRECTION':
                        $obj->to = (string) $journeyAttribute->Attribute->AttributeVariant->Text;
                        break;
                }
            }
        }

        $capacities1st = [];
        $capacities2nd = [];

        if ($xml->PassList->BasicStop) {
            foreach ($xml->PassList->BasicStop as $basicStop) {
                if ($basicStop->Arr || $basicStop->Dep) {
                    $stop = Stop::createFromXml($basicStop, $date, null);
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

        if (count($capacities1st) > 0) {
            $obj->capacity1st = max($capacities1st);
        }
        if (count($capacities2nd) > 0) {
            $obj->capacity2nd = max($capacities2nd);
        }

        return $obj;
    }

    public static function createFromJson($json, $obj = null)
    {
        if (!$obj) {
            $obj = new self();
        }

        if (isset($json->number)) {
            $obj->name = $json->number;
            $obj->number = $json->number;
        }
        if (isset($json->{'*Z'})) {
            $obj->name = $json->{'*Z'};
            $obj->number = $json->{'*Z'};
        }
        if (isset($json->{'*L'})) {
            $obj->number = $json->{'*L'};
        }
        if (isset($json->line)) {
            $obj->category = $json->line;
        }
        if (isset($json->{'*G'})) {
            $obj->category = $json->{'*G'};
        }
        if (isset($json->terminal)) {
            if (isset($json->terminal->name)) {
                $obj->to = $json->terminal->name;
            } else {
                $obj->to = $json->terminal;
            }
        }
        if (isset($json->operator)) {
            $obj->operator = $json->operator;
        }

        $obj->passList[] = Stop::createFromJson($json);
        if (isset($json->stops)) {
            foreach ($json->stops as $stop) {
                $obj->passList[] = Stop::createFromJson($stop);
            }
        }
        if (isset($json->subsequent_stops)) {
            foreach ($json->subsequent_stops as $stop) {
                $obj->passList[] = Stop::createFromJson($stop);
            }
        }
        if (isset($json->exit)) {
            $obj->passList[] = Stop::createFromJson($json->exit);
        }

        return $obj;
    }
}
