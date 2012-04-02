<?php

namespace Transport\Entity\Schedule;

use Transport\Entity\Query;
use Transport\Entity\Transportations;
use Transport\Entity\Location\Station;

class StationBoardQuery extends Query
{
    /**
     * @var Station
     */
    public $station;

    public $boardType = 'DEP';

    public $maxJourneys = 40;

    public $date;

    public $transportations = array('all');

    public function __construct(Station $station, \DateTime $date = null)
    {
        $this->station = $station;

        if (!($date instanceof \DateTime)) {
            $date = new \DateTime('now', new \DateTimeZone('Europe/Zurich'));
        }
        $this->date = $date;
    }

    public function toXml()
    {
        $request = $this->createRequest('STBReq');

        $board = $request->addChild('STBReq');

        $board->addAttribute('boardType', $this->boardType);
        $board->addAttribute('maxJourneys', $this->maxJourneys);
        $board->addChild('Time', $this->date->format('H:i'));

        $period = $board->addChild('Period');
        $dateBegin = $period->addChild('DateBegin');
        $dateBegin->addChild('Date', $this->date->format('Ymd'));
        $dateEnd = $period->addChild('DateEnd');
        $dateEnd->addChild('Date', $this->date->format('Ymd'));

        $tableStation = $board->addChild('TableStation');
        $tableStation->addAttribute('externalId', $this->station->id);
        $board->addChild('ProductFilter', Transportations::reduceTransportations($this->transportations));

        return $request->asXML();
    }

}
