<?php

namespace Transport\Test;

use Buzz\Message\Response;

use Transport\Entity\Location\LocationQuery;

class APITest extends \PHPUnit_Framework_TestCase
{
    protected function setUp()
    {
        $this->browser = $this->getMock('Buzz\\Browser', array('post'));

        $this->api = new \Transport\API($this->browser);
    }

    public function testFindLocationsArray()
    {
        $response = new Response();
        $response->setContent(file_get_contents(__DIR__ . '/../../fixtures/location.xml'));
    
        $this->browser->expects($this->once())
            ->method('post')
            ->with(
                $this->equalTo('http://xmlfahrplan.sbb.ch/bin/extxml.exe/'),
                $this->equalTo(array(
                    'User-Agent: SBBMobile/4.2 CFNetwork/485.13.9 Darwin/11.0.0',
                    'Accept: application/xml',
                    'Content-Type: application/xml'
                )),
                $this->equalTo('<?xml version="1.0" encoding="utf-8"?>
<ReqC lang="EN" prod="iPhone3.1" ver="2.3" accessId="MJXZ841ZfsmqqmSymWhBPy5dMNoqoGsHInHbWJQ5PTUZOJ1rLTkn8vVZOZDFfSe"><LocValReq id="from" sMode="1"><ReqLoc match="Zürich" type="ALLTYPE"/></LocValReq><LocValReq id="to" sMode="1"><ReqLoc match="Bern" type="ALLTYPE"/></LocValReq></ReqC>
')
            )
            ->will($this->returnValue($response));
        
        $locations = $this->api->findLocations(new LocationQuery(array('from' => 'Zürich', 'to' => 'Bern')));

        $this->assertEquals(2, count($locations));
        $this->assertEquals(34, count($locations['from']));
        $this->assertEquals('Zuerich', $locations['from'][0]->name);
        $this->assertEquals('Zürich HB', $locations['from'][3]->name);
        $this->assertEquals('47450378', $locations['from'][4]->coordinate->y);
        $this->assertEquals(1, count($locations['to']));
        $this->assertEquals('Bern', $locations['to'][0]->name);
        $this->assertEquals('008507000', $locations['to'][0]->id);
        $this->assertEquals('46948825', $locations['to'][0]->coordinate->y);
    }
}
