<?php

namespace Transport\Entity\Schedule;

use Buzz\Message\Form\FormRequest;
use Transport\Entity\Location\Station;
use Transport\Entity\Query;
use Transport\Entity\Transportations;

class StationBoardQuery extends Query
{
    /**
     * @var Station
     */
    public $station;

    public $boardType = 'departure';

    public $maxJourneys = 40;

    public $date;

    public $transportations = ['all'];

    public function __construct(Station $station, \DateTime $date = null)
    {
        $this->station = $station;

        if (!($date instanceof \DateTime)) {
            $date = new \DateTime('now', new \DateTimeZone('Europe/Zurich'));
        }
        $this->date = $date;
    }

    public function toFormRequest()
    {
        $request = new FormRequest(FormRequest::METHOD_GET, \Transport\API::URL . 'stationboard.json');
        $request->setField('stop', $this->station->name);
        $request->setField('date', $this->date->format('Y-m-d'));
        $request->setField('time', $this->date->format('H:i'));
        $request->setField('mode', $this->boardType === 'arrival' ? 'arrival' : 'depart');
        $request->setField('limit', $this->maxJourneys);
        $request->setField('show_tracks', '1');
        $request->setField('show_subsequent_stops', '1');

        return $request;
    }

    public function toXml()
    {
        $request = $this->createRequest();

        $board = $request->addChild('STBReq');

        if ($this->boardType === 'arrival') {
            $boardType = 'ARR';
        } else {
            $boardType = 'DEP';
        }
        $board->addAttribute('boardType', $boardType);

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
