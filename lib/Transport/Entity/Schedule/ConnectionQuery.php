<?php

namespace Transport\Entity\Schedule;

use Buzz\Message\Form\FormRequest;
use Transport\Entity\Location\Location;
use Transport\Entity\Query;
use Transport\Entity\Transportations;

class ConnectionQuery extends Query
{
    const ACCESSIBILITY_INDEPENDENT_BOARDING = 'independent_boarding';

    const ACCESSIBILITY_ASSISTED_BOARDING = 'assisted_boarding';

    const ACCESSIBILITY_ADVANCED_NOTICE = 'advanced_notice';

    public $srcLocation;

    public $dstLocation;

    public $viaLocations;

    public $date;

    public $time;

    public $isArrivalTime = false;

    public $transportations = ['all'];

    public $limit = 4;

    public $page = 0;

    public $searchMode = \Transport\API::SEARCH_MODE_NORMAL;

    public $changeCount = -1;

    public $changeExtensionPercent = 0;

    public $direct = false;

    public $sleeper = false;

    public $couchette = false;

    public $bike = false;

    public $accessibility = null;

    public function __construct(Location $srcLocation, Location $dstLocation, array $viaLocations = [], $date = null, $time = null)
    {
        $this->srcLocation = $srcLocation;
        $this->dstLocation = $dstLocation;
        $this->viaLocations = $viaLocations;

        $this->date = $date ?: date('Y-m-d');
        $this->time = $time ?: date('H:i');
    }

    public function toFormRequest()
    {
        $request = new FormRequest(FormRequest::METHOD_GET, \Transport\API::URL.'route.json');
        $request->setField('from', $this->srcLocation->name);
        $request->setField('to', $this->dstLocation->name);
        $request->setField('via', $this->viaLocations);
        $request->setField('date', date('Y-m-d', strtotime($this->date)));
        $request->setField('time', date('H:i', strtotime($this->time)));
        $request->setField('time_type', $this->isArrivalTime ? 'arrival' : 'departure');
        if ($this->page >= 0) {
            $request->setField('num', ($this->page + 1) * $this->limit);
        } else {
            $request->setField('pre', abs($this->page) * $this->limit);
        }
        $request->setField('show_delays', '1');

        return $request;
    }

    public function toXml()
    {
        if ($this->isArrivalTime === false) {
            $forwardCount = $this->limit;
            $backwardCount = 0;
        } else {
            $forwardCount = 0;
            $backwardCount = $this->limit;
        }

        $transportationsBinary = Transportations::reduceTransportations($this->transportations);

        $request = $this->createRequest();

        $con = $request->addChild('ConReq');

        $start = $con->addChild('Start');
        $this->srcLocation->toXml($start);

        $prod = $start->addChild('Prod');
        $prod['prod'] = $transportationsBinary;

        if ($this->direct) {
            $prod['direct'] = 1;
        }

        if ($this->sleeper) {
            $prod['sleeper'] = 1;
        }

        if ($this->couchette) {
            $prod['couchette'] = 1;
        }

        if ($this->bike) {
            $filterList = $con->addChild('FilterList');
            $attrFilter = $filterList->addChild('ConReqAttrFilter');
            $attrFilter['mode'] = '1';
            $attrFilter['type'] = 'EXC';
            $attrFilter['value'] = 'VN:VX';
        }

        if ($this->accessibility === self::ACCESSIBILITY_INDEPENDENT_BOARDING) {
            $con['HandicapProfile'] = '1';
        }
        if ($this->accessibility === self::ACCESSIBILITY_ASSISTED_BOARDING) {
            $con['HandicapProfile'] = '2';
        }
        if ($this->accessibility === self::ACCESSIBILITY_ADVANCED_NOTICE) {
            $con['HandicapProfile'] = '3';
        }

        $dest = $con->addChild('Dest');
        $this->dstLocation->toXml($dest);

        foreach ($this->viaLocations as $location) {
            $via = $con->addChild('Via');
            $location->toXml($via);
            $prod = $via->addChild('Prod');
            $prod['prod'] = $transportationsBinary;
        }

        $reqt = $con->addChild('ReqT');
        if ($this->isArrivalTime) {
            $reqt['a'] = 1;
        } else {
            $reqt['a'] = 0;
        }
        $reqt['date'] = date('Ymd', strtotime($this->date));
        $reqt['time'] = date('H:i', strtotime($this->time));

        $rflags = $con->addChild('RFlags');
        $rflags['b'] = $backwardCount;
        $rflags['f'] = $forwardCount;
        $rflags['sMode'] = $this->searchMode;
        if ($this->changeCount >= 0) {
            $rflags['nrChanges'] = $this->changeCount;
        }
        if ($this->changeExtensionPercent > 0) {
            $rflags['chExtension'] = $this->changeExtensionPercent;
        }

        return $request->asXML();
    }
}
