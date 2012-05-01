<?php

namespace Transport\Entity\Schedule;

use Transport\Entity\Query;
use Transport\Entity\Transportations;
use Transport\Entity\Location\Location;

class MoreConnectionQuery extends Query
{

    public $connetionReference = null;
    public $forwardCount = null;
    public $backwardCount = null;

    public function __construct($connetionReference, $forwardCount)
    {
        $this->connetionReference = $connetionReference;
        $this->forwardCount = $forwardCount;
    }

    public function toXml()
    {
        $request = $this->createRequest();

        $con = $request->addChild('ConScrReq');
        // @TODO: Implement backward search in time $con['scrDir'] = 'B';
        $con['scrDir'] = 'F';
        $con['nrCons'] = $this->forwardCount;

        $con->addChild('ConResCtxt', $this->connetionReference);

        return $request->asXML();
    }

}
