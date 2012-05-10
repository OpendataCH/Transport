<?php

namespace Transport\Entity\Schedule;

use Transport\Entity\Query;
use Transport\Entity\Schedule\IConnectionQuery;
use Transport\Entity\Transportations;
use Transport\Entity\Location\Location;

class MoreConnectionQuery extends Query implements IConnectionQuery
{

    public $connectionReference = null;
    public $connectionCount = null;
    public $direction = null;

    public function __construct($connectionReference, $connectionCount = 6, $direction = 'F')
    {
        $this->connectionReference = $connectionReference;
        $this->connectionCount = $connectionCount;
        $this->direction = $direction;
    }

    public function toXml()
    {
        $request = $this->createRequest();

        $con = $request->addChild('ConScrReq');
        $con['scrDir'] = $this->direction;
        $con['nrCons'] = $this->connectionCount;

        $con->addChild('ConResCtxt', $this->connectionReference);

        return $request->asXML();
    }

}
?>