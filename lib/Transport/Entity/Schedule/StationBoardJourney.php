<?php

namespace Transport\Entity\Schedule;

/**
 * Request for a station board journey.
 *
 * @SWG\Definition()
 */
class StationBoardJourney
{
    /**
     * @var \Transport\Entity\Schedule\Stop
     * @SWG\Property()
     */
    public $stop;

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

    /**
     * @param \SimpleXMLElement   $xml
     * @param \DateTime           $date The date that will be assigned to this journey
     * @param StationBoardJourney $obj  An optional existing journey to overwrite
     *
     * @return StationBoardJourney
     */
    public static function createStationBoardFromXml(\SimpleXMLElement $xml, \DateTime $date, self $obj = null)
    {
        if (!$obj) {
            $obj = new self();
        }

        $stop = Stop::createFromXml($xml->MainStop->BasicStop, $date, null);

        // use resolved date from main stop
        if ($stop->departure) {
            $date = new \DateTime($stop->departure);
        } else {
            $date = new \DateTime($stop->arrival);
        }

        /* @var $obj StationBoardJourney */
        $obj = Journey::createFromXml($xml, $date, $obj);

        $obj->stop = $stop;

        return $obj;
    }

    public static function createFromJson($json, Journey $obj = null)
    {
        if (!$obj) {
            $obj = new self();
        }

        $stop = Stop::createFromJson($json, null);

        /* @var $obj StationBoardJourney */
        $obj = Journey::createFromJson($json, $obj);

        $obj->stop = $stop;

        return $obj;
    }
}
