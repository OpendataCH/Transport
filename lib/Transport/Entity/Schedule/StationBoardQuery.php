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

    public function __construct(Station $station, $date = null)
    {
        $this->station = $station;

        $this->date = $date ?: date('c');
    }

    public function toXml()
    {
        $request = $this->createRequest('STBReq');

        $board = $request->addChild('STBReq');

        $board->addAttribute('boardType', $this->boardType);
        $board->addAttribute('maxJourneys', $this->maxJourneys);
        $board->addChild('Time', date('H:i', strtotime($this->date)));

        $period = $board->addChild('Period');
        $dateBegin = $period->addChild('DateBegin');
        $dateBegin->addChild('Date', date('Ymd', strtotime($this->date)));
        $dateEnd = $period->addChild('DateEnd');
        $dateEnd->addChild('Date', date('Ymd', strtotime($this->date)));

        $tableStation = $board->addChild('TableStation');
        $tableStation->addAttribute('externalId', $this->station->id);
        $board->addChild('ProductFilter', Transportations::reduceTransportations($this->transportations));

        return $request->asXML();
    }
}
