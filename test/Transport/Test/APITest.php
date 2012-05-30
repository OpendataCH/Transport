<?php

namespace Transport\Test;

use Buzz\Message\Response;
use Transport\Entity\Location\LocationQuery;
use Transport\Entity\Location\NearbyQuery;
use Transport\Entity\Location\Station;
use Transport\Entity\Schedule\StationBoardQuery;

class APITest extends \PHPUnit_Framework_TestCase
{
    protected function setUp()
    {
        $this->browser = $this->getMock('Buzz\\Browser', array('post', 'get'));

        $this->api = new \Transport\API($this->browser);
    }

    public function testFindLocationsArray()
    {
        $response = new Response();
        $response->setContent(file_get_contents(__DIR__ . '/../../fixtures/location.xml'));

        $this->browser->expects($this->once())
            ->method('post')
            ->with(
                $this->equalTo('http://fahrplan.sbb.ch/bin/extxml.exe/'),
                $this->equalTo(array(
                        'User-Agent: SBBMobile/4.2 CFNetwork/485.13.9 Darwin/11.0.0',
                        'Accept: application/xml',
                        'Content-Type: application/xml'
                )),
                $this->equalTo('<?xml version="1.0" encoding="iso-8859-1"?>
<ReqC lang="EN" prod="iPhone3.1" ver="2.3" accessId="MJXZ841ZfsmqqmSymWhBPy5dMNoqoGsHInHbWJQ5PTUZOJ1rLTkn8vVZOZDFfSe"><LocValReq id="from" sMode="1"><ReqLoc match="Z�rich" type="ALLTYPE"/></LocValReq><LocValReq id="to" sMode="1"><ReqLoc match="Bern" type="ALLTYPE"/></LocValReq></ReqC>
')
            )
            ->will($this->returnValue($response));

        $locations = $this->api->findLocations(new LocationQuery(array('from' => 'Zürich', 'to' => 'Bern')));

        $this->assertEquals(2, count($locations));
        $this->assertEquals(34, count($locations['from']));
        $this->assertEquals('Zuerich', $locations['from'][0]->name);
        $this->assertEquals('Zürich HB', $locations['from'][3]->name);
        $this->assertEquals(47.450378, $locations['from'][4]->coordinate->y);
        $this->assertEquals(1, count($locations['to']));
        $this->assertEquals('Bern', $locations['to'][0]->name);
        $this->assertEquals('008507000', $locations['to'][0]->id);
        $this->assertEquals(46.948825, $locations['to'][0]->coordinate->y);
    }

    public function testFindNearbyLocationsArray()
    {
        $response = new Response();
        $response->setContent(file_get_contents(__DIR__ . '/../../fixtures/location.json'));

        $this->browser->expects($this->once())
                ->method('get')
                ->with(
                        $this->equalTo(
                                'http://fahrplan.sbb.ch/bin/query.exe/dny?performLocating=2&tpl=stop2json&look_maxno=2&look_stopclass=1023&look_maxdist=5000&look_y=47003057&look_x=8382324'
                        )
                )
                ->will($this->returnValue($response));

        $stations = $this->api->findNearbyLocations(new NearbyQuery('47.003057', '8.382324', 2));

        $this->assertEquals(2, count($stations));
        $this->assertEquals(8508489, $stations[0]->id);
        $this->assertEquals('Kehrsiten-Bürgenstock', $stations[0]->name);
        $this->assertEquals(8.382324, $stations[0]->coordinate->x);
        $this->assertEquals(47.003057, $stations[0]->coordinate->y);
        $this->assertEquals('WGS84', $stations[0]->coordinate->type);
        $this->assertEquals('Bürgenstock, Hotels', $stations[1]->name);
        $this->assertEquals(8.386252, $stations[1]->coordinate->x);
        $this->assertEquals(46.997088, $stations[1]->coordinate->y);
        $this->assertEquals('WGS84', $stations[1]->coordinate->type);
    }

    public function testGetStationBoard() {
        $response = new Response();
        $response->setContent(file_get_contents(__DIR__ . '/../../fixtures/stationboard.xml'));

        $this->browser->expects($this->once())
            ->method('post')
            ->with(
                $this->equalTo('http://fahrplan.sbb.ch/bin/extxml.exe/'),
                $this->equalTo(array(
                        'User-Agent: SBBMobile/4.2 CFNetwork/485.13.9 Darwin/11.0.0',
                        'Accept: application/xml',
                        'Content-Type: application/xml'
                )),
                $this->equalTo('<?xml version="1.0" encoding="iso-8859-1"?>
<ReqC lang="EN" prod="iPhone3.1" ver="2.3" accessId="MJXZ841ZfsmqqmSymWhBPy5dMNoqoGsHInHbWJQ5PTUZOJ1rLTkn8vVZOZDFfSe"><STBReq boardType="DEP" maxJourneys="40"><Time>23:55</Time><Period><DateBegin><Date>20120213</Date></DateBegin><DateEnd><Date>20120213</Date></DateEnd></Period><TableStation externalId="008591052"/><ProductFilter>1111111111111111</ProductFilter></STBReq></ReqC>
')
            )
            ->will($this->returnValue($response));

        $station = new Station('008591052'); // Zürich, Bäckeranlage
        $journeys = $this->api->getStationBoard(new StationBoardQuery($station, \DateTime::createFromFormat(\DateTime::ISO8601, '2012-02-13T23:55:00+01:00')));

        $this->assertEquals(3, count($journeys));
        $this->assertEquals('2012-02-13T23:57:00+0100', $journeys[0]->stop->departure);
        $this->assertEquals('2012-02-13T23:58:00+0100', $journeys[1]->stop->departure);
        $this->assertEquals('2012-02-14T04:41:00+0100', $journeys[2]->stop->departure);
    }
}
