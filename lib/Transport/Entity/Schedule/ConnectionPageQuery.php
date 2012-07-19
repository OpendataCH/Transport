<?php 

namespace Transport\Entity\Schedule;

use Transport\Entity\Query;
use Transport\Entity\Transportations;
use Transport\Entity\Location\Location;

class ConnectionPageQuery extends Query
{
    /**
     * @var ConnectionQuery
     */
    public $query;

    public $context;

    public function __construct(ConnectionQuery $query, $context)
    {
        $this->query = $query;
        $this->context = $context;
    }

    public function toXml()
    {
        $request = $this->createRequest();

        $conScr = $request->addChild('ConScrReq');
        $conScr['scrDir'] = $this->query->page < 0 ? 'B' : 'F';
        $conScr['nrCons'] = $this->query->limit;

        $context = $conScr->addChild('ConResCtxt', $this->context);

        return $request->asXML();
    }
}
