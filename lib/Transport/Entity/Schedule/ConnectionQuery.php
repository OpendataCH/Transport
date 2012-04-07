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

    public $dateType = \Transport\API::DATE_TYPE_DEPARTURE;

    public $transportations = array('all');

    public $forwardCount= null;

    public $backwardCount = null;

    public $searchMode = \Transport\API::SEARCH_MODE_NORMAL;

    public $changeCount = -1;

    public $changeExtensionPercent = 0;
    
    public $direct = 0;
    
    public $sleeper = 0;

    public $couchette = 0;
    
    public $bike = 0;    
        
    public function __construct(Location $srcLocation, Location $dstLocation, $viaLocations = array(), $date = null, $time = null)
    {
        $this->srcLocation = $srcLocation;
        $this->dstLocation = $dstLocation;
        $this->viaLocations = $viaLocations;

        $this->date = $date ?: date('Y-m-d');
        $this->time = $time ?: date('H:i');
    }

    public function toXml()
    {
        if ($this->forwardCount === null && $this->backwardCount === null) {
            if ($this->dateType == \Transport\API::DATE_TYPE_DEPARTURE) {
                $forwardCount = 4;
                $backwardCount = 0;
            } else {
                $forwardCount = 0;
                $backwardCount = 4;
            }
        } else {
            $forwardCount = $this->forwardCount;
            $backwardCount = $this->backwardCount;
        }

        $transportationsBinary = Transportations::reduceTransportations($this->transportations);

        $request = $this->createRequest();

        $con = $request->addChild('ConReq');

        $start = $con->addChild('Start');
        $this->srcLocation->toXml($start);

        $prod = $start->addChild('Prod');
        $prod['prod'] = $transportationsBinary;

        if ($this->direct > 0) {
            $prod['direct'] = 1;    
        }
        
        if ($this->sleeper > 0) {
            $prod['sleeper'] = 1;
        }
        
        if ($this->couchette > 0) {
            $prod['couchette'] = 1;    
        }
        
        if ($this->bike > 0) {
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
        $reqt['a'] = $this->dateType;
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
        var_dump($request->asXML());
        return $request->asXML();
    }
}
