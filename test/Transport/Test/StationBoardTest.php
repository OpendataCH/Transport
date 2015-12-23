<?php

namespace Transport\Test;

use Buzz\Message\Response;

class StationBoardTest extends IntegrationTest
{
    public function testGetStationBoard()
    {
        $responseLocation = new Response();
        $responseLocation->setContent($this->getFixture('stationboard/response_location.xml'));

        $responseStationBoard = new Response();
        $responseStationBoard->setContent($this->getFixture('stationboard/response_stationboard-2012-02-13.xml'));

        $this->getBrowser()->expects($this->any())
            ->method('post')
            ->withConsecutive(
                array($this->anything(), $this->anything(), $this->equalTo($this->getXmlFixture('stationboard/request_location.xml'))),
                array($this->anything(), $this->anything(), $this->equalTo($this->getXmlFixture('stationboard/request_stationboard-2012-02-13.xml')))
            )
            ->will($this->onConsecutiveCalls($responseLocation, $responseStationBoard));

        $client = $this->createClient();
        $crawler = $client->request('GET', '/v1/stationboard', array(
            'station' => '008591052',
            'limit' => '3',
            'datetime' => '2012-02-13T23:55:00',
        ));

        $this->assertEquals($this->getFixture('stationboard/response_stationboard-2012-02-13.json'), $this->json($client->getResponse()));
        $this->assertTrue($client->getResponse()->isOk());
    }
}
