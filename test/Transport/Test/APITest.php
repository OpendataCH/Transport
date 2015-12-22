<?php

namespace Transport\Test;

use Buzz\Message\Response;
use Transport\Entity\Location\LocationQuery;
use Transport\Entity\Location\NearbyQuery;
use Transport\Entity\Location\Station;
use Transport\Entity\Schedule\StationBoardQuery;
use Transport\Entity\Schedule\ConnectionQuery;

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
                        'User-Agent: SBBMobile/4.8 CFNetwork/609.1.4 Darwin/13.0.0',
                        'Accept: application/xml',
                        'Content-Type: application/xml'
                )),
                $this->equalTo(utf8_decode('<?xml version="1.0" encoding="iso-8859-1"?>
<ReqC lang="EN" prod="iPhone3.1" ver="2.3" accessId="vWjygiRIy0uclbLz4qDO7S3G4dcIIViwoLFCZlopGhe88vlsfedGIqctZP9lvqb"><LocValReq id="from" sMode="1"><ReqLoc match="Zürich" type="ALLTYPE"/></LocValReq><LocValReq id="to" sMode="1"><ReqLoc match="Bern" type="ALLTYPE"/></LocValReq></ReqC>
'))
            )
            ->will($this->returnValue($response));

        $locations = $this->api->findLocations(new LocationQuery(array('from' => 'Zürich', 'to' => 'Bern')));

        $this->assertEquals(2, count($locations));
        $this->assertEquals(41, count($locations['from']));
        $this->assertEquals('Zürich', $locations['from'][0]->name);
        $this->assertEquals('Zürich HB', $locations['from'][1]->name);
        $this->assertEquals(8.540192, $locations['from'][0]->coordinate->y);
        $this->assertEquals(1, count($locations['to']));
        $this->assertEquals('Bern', $locations['to'][0]->name);
        $this->assertEquals('008507000', $locations['to'][0]->id);
        $this->assertEquals(7.439122, $locations['to'][0]->coordinate->y);
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
        $this->assertEquals(47.003066, $stations[0]->coordinate->x);
        $this->assertEquals(8.382324, $stations[0]->coordinate->y);
        $this->assertEquals('WGS84', $stations[0]->coordinate->type);
        $this->assertEquals('Obbürgen, Unter-Misli', $stations[1]->name);
        $this->assertEquals(46.994616, $stations[1]->coordinate->x);
        $this->assertEquals(8.385892, $stations[1]->coordinate->y);
        $this->assertEquals('WGS84', $stations[1]->coordinate->type);
    }

    public function testFindNearbyLocationsNyon()
    {
        $response = new Response();
        $response->setContent(file_get_contents(__DIR__ . '/../../fixtures/location-nyon.json'));

        $this->browser->expects($this->once())
            ->method('get')
            ->with(
                $this->equalTo(
                    'http://fahrplan.sbb.ch/bin/query.exe/dny?performLocating=2&tpl=stop2json&look_maxno=1&look_stopclass=1023&look_maxdist=5000&look_y=46388653&look_x=6238729'
                )
            )
            ->will($this->returnValue($response));

        $stations = $this->api->findNearbyLocations(new NearbyQuery('46.388653', '6.238729', 1));

        $this->assertEquals(1, count($stations));
        $this->assertEquals(8593897, $stations[0]->id);
        $this->assertEquals("Nyon, rte de l'Etraz", $stations[0]->name);
        $this->assertEquals(46.388635, $stations[0]->coordinate->x);
        $this->assertEquals(6.238738, $stations[0]->coordinate->y);
        $this->assertEquals('WGS84', $stations[0]->coordinate->type);
    }

    public function testGetStationBoard() {
        $response = new Response();
        $response->setContent(file_get_contents(__DIR__ . '/../../fixtures/archive/stationboard-2012-02-13.xml'));

        $this->browser->expects($this->once())
            ->method('post')
            ->with(
                $this->equalTo('http://fahrplan.sbb.ch/bin/extxml.exe/'),
                $this->equalTo(array(
                        'User-Agent: SBBMobile/4.8 CFNetwork/609.1.4 Darwin/13.0.0',
                        'Accept: application/xml',
                        'Content-Type: application/xml'
                )),
                $this->equalTo('<?xml version="1.0" encoding="iso-8859-1"?>
<ReqC lang="EN" prod="iPhone3.1" ver="2.3" accessId="vWjygiRIy0uclbLz4qDO7S3G4dcIIViwoLFCZlopGhe88vlsfedGIqctZP9lvqb"><STBReq boardType="DEP" maxJourneys="40"><Time>23:55</Time><Period><DateBegin><Date>20120213</Date></DateBegin><DateEnd><Date>20120213</Date></DateEnd></Period><TableStation externalId="008591052"/><ProductFilter>1111111111111111</ProductFilter></STBReq></ReqC>
')
            )
            ->will($this->returnValue($response));

        $station = new Station('008591052'); // Z√ºrich, B√§ckeranlage
        $journeys = $this->api->getStationBoard(new StationBoardQuery($station, \DateTime::createFromFormat(\DateTime::ISO8601, '2012-02-13T23:55:00+01:00')));

        $this->assertEquals(3, count($journeys));
        $this->assertEquals('2012-02-13T23:57:00+0100', $journeys[0]->stop->departure);
        $this->assertEquals('2012-02-13T23:58:00+0100', $journeys[1]->stop->departure);
        $this->assertEquals('2012-02-14T04:41:00+0100', $journeys[2]->stop->departure);
    }

    public function testGetStationBoardDelay() {
        $response = new Response();
        $response->setContent(file_get_contents(__DIR__ . '/../../fixtures/archive/stationboard-2013-10-15.xml'));

        $this->browser->expects($this->once())
            ->method('post')
            ->with(
                $this->equalTo('http://fahrplan.sbb.ch/bin/extxml.exe/'),
                $this->equalTo(array(
                        'User-Agent: SBBMobile/4.8 CFNetwork/609.1.4 Darwin/13.0.0',
                        'Accept: application/xml',
                        'Content-Type: application/xml'
                )),
                $this->equalTo('<?xml version="1.0" encoding="iso-8859-1"?>
<ReqC lang="EN" prod="iPhone3.1" ver="2.3" accessId="vWjygiRIy0uclbLz4qDO7S3G4dcIIViwoLFCZlopGhe88vlsfedGIqctZP9lvqb"><STBReq boardType="DEP" maxJourneys="40"><Time>22:20</Time><Period><DateBegin><Date>20131015</Date></DateBegin><DateEnd><Date>20131015</Date></DateEnd></Period><TableStation externalId="008591052"/><ProductFilter>1111111111111111</ProductFilter></STBReq></ReqC>
')
            )
            ->will($this->returnValue($response));

        $station = new Station('008591052'); // Z√ºrich, B√§ckeranlage
        $journeys = $this->api->getStationBoard(new StationBoardQuery($station, \DateTime::createFromFormat(\DateTime::ISO8601, '2013-10-15T22:20:00+01:00')));

        $this->assertEquals(1, count($journeys));
        $this->assertEquals('2013-10-15T22:10:00+0100', $journeys[0]->stop->departure);
        $this->assertEquals(12, $journeys[0]->stop->delay);
    }

    /**
     * @expectedException Exception
     * @expectedExceptionMessage Error from fahrplan.sbb.ch: F2 - Spool: Error writing the spoolfile.
     */
    public function testFindConnectionsError()
    {
        $response = new Response();
        $response->setContent(file_get_contents(__DIR__ . '/../../fixtures/error.xml'));

        $this->browser->expects($this->once())
            ->method('post')
            ->with(
                $this->equalTo(
                    'http://fahrplan.sbb.ch/bin/extxml.exe/'
                )
            )
            ->will($this->returnValue($response));

        $from = new Station('008503000');
        $to = new Station('008503504');
        $query = new ConnectionQuery($from, $to, array(), '2012-02-13T23:55:00+01:00');

        $this->api->findConnections($query);
    }

    /**
     * @expectedException Exception
     * @expectedExceptionMessageRegExp /Invalid XML from fahrplan\.sbb\.ch/
     */
    public function testFindConnections500()
    {
        $response = new Response();
        $response->setContent(file_get_contents(__DIR__ . '/../../fixtures/500.xml'));

        $this->browser->expects($this->once())
            ->method('post')
            ->with(
                $this->equalTo(
                    'http://fahrplan.sbb.ch/bin/extxml.exe/'
                )
            )
            ->will($this->returnValue($response));

        $from = new Station('008503000');
        $to = new Station('008503504');
        $query = new ConnectionQuery($from, $to, array(), '2012-02-13T23:55:00+01:00');

        $this->api->findConnections($query);
    }
}
