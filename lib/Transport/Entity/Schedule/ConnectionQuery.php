<?php 

namespace Transport\Entity\Schedule;

use Transport\Entity\Query;
use Transport\Entity\Transportations;
use Transport\Entity\Location\Location;

class ConnectionQuery extends Query
{
    public $srcLocation;

    public $dstLocation;

    public $viaLocations;

    public $date;

    public $time;
    
    public $isArrivalTime = false;

    public $transportations = array('all');

    public $limit = 4;

    public $page = 0;

    public $searchMode = \Transport\API::SEARCH_MODE_NORMAL;

    public $changeCount = -1;

    public $changeExtensionPercent = 0;

    public $direct = false;

    public $sleeper = false;

    public $couchette = false;

    public $bike = false;

    public function __construct(Location $srcLocation, Location $dstLocation, array $viaLocations = array(), $date = null, $time = null)
    {
        $this->srcLocation = $srcLocation;
        $this->dstLocation = $dstLocation;
        $this->viaLocations = $viaLocations;

        $this->date = $date ?: date('Y-m-d');
        $this->time = $time ?: date('H:i');
    }

    public function toXml()
    {
        if ($this->isArrivalTime == false) {
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
            $prod['bike'] = 1;    
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
