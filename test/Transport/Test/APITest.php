<?php

namespace Transport\Test;

use Buzz\Message\Response;
use Transport\Entity\Location\LocationQuery;
use Transport\Entity\Location\NearbyQuery;
use Transport\Entity\Location\Station;
use Transport\Entity\Schedule\ConnectionQuery;

class APITest extends \PHPUnit_Framework_TestCase
{
    protected function setUp()
    {
        $this->browser = $this->getMock('Buzz\\Browser', array('post', 'get'));

        $this->api = new \Transport\API($this->browser);
    }
}
