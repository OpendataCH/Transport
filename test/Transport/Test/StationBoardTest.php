<?php

namespace Transport\Test;

use Buzz\Message\Response;

class StationBoardTest extends IntegrationTest
{
    private $url = 'http://fahrplan.sbb.ch/bin/extxml.exe/';

    private $headers = [
        'User-Agent: SBBMobile/4.8 CFNetwork/609.1.4 Darwin/13.0.0',
        'Accept: application/xml',
        'Content-Type: application/xml',
    ];

    public function stationBoardProvider()
    {
        return [
            [['station' => '008591052', 'limit' => '3', 'datetime' => '2012-02-13T23:57:30'], 'hafas_request_2012-02-13.xml', 'hafas_response_2012-02-13.xml', 'response_2012-02-13.json'],
            [['station' => '008591052', 'limit' => '3', 'datetime' => '2013-10-15T22:20:00'], 'hafas_request_2013-10-15.xml', 'hafas_response_2013-10-15.xml', 'response_2013-10-15.json'], // delay
            [['station' => '008591052', 'limit' => '3', 'datetime' => '2015-12-23T14:20:00'], 'hafas_request_2015-12-23.xml', 'hafas_response_2015-12-23.xml', 'response_2015-12-23.json'],
            [['station' => '008591052', 'limit' => '1', 'datetime' => '2016-01-17T23:30:00'], 'hafas_request_2016-01-17.xml', 'hafas_response_2016-01-17.xml', 'response_2016-01-17.json'], // midnight delay
            [['station' => '008591052', 'limit' => '3', 'datetime' => '2016-01-19T23:47:00'], 'hafas_request_2016-01-19.xml', 'hafas_response_2016-01-19.xml', 'response_2016-01-19.json'], // delay after midnight
            [['station' => '008591052', 'limit' => '1', 'datetime' => '2017-01-12T19:06:00', 'type' => 'arrival'], 'hafas_request_2017-01-12.xml', 'hafas_response_2017-01-12.xml', 'response_2017-01-12.json'], // delayed arrival
            [['station' => '008591052', 'limit' => '3', 'datetime' => '2016-12-23T14:20:00'], 'hafas_request_2016-12-23.xml', 'hafas_response_2016-12-23.xml', 'response_2016-12-23.json'],
        ];
    }

    /**
     * @dataProvider stationBoardProvider
     */
    public function testGetStationBoard($parameters, $hafasRequest, $hafasResponse, $response)
    {
        $responseLocation = new Response();
        $responseLocation->setContent($this->getFixture('stationboard/hafas_response_location.xml'));

        $responseStationBoard = new Response();
        $responseStationBoard->setContent($this->getFixture('stationboard/'.$hafasResponse));

        $this->getBrowser()->expects($this->any())
            ->method('post')
            ->withConsecutive(
                [$this->equalTo($this->url), $this->equalTo($this->headers), $this->equalTo($this->getXmlFixture('stationboard/hafas_request_location.xml'))],
                [$this->equalTo($this->url), $this->equalTo($this->headers), $this->equalTo($this->getXmlFixture('stationboard/'.$hafasRequest))]
            )
            ->will($this->onConsecutiveCalls($responseLocation, $responseStationBoard));

        $client = $this->createClient();
        $client->request('GET', '/v1/stationboard', $parameters);

        $this->assertEquals($this->getFixture('stationboard/'.$response), $this->json($client->getResponse()));
        $this->assertTrue($client->getResponse()->isOk());
    }
}
