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
            [['station' => '008591052', 'limit' => '3', 'datetime' => '2015-12-23T14:20:00'], 'hafas_request_2015-12-23.xml', 'searchch_response_2016-12-23.json', 'response_2016-12-23.json'],
        ];
    }

    /**
     * @dataProvider stationBoardProvider
     */
    public function testGetStationBoard($parameters, $hafasRequest, $hafasResponse, $response)
    {
        $responseStationBoard = new Response();
        $responseStationBoard->setContent($this->getFixture('stationboard/'.$hafasResponse));

        $this->getBrowser()->expects($this->any())
            ->method('send')
            ->willReturn($responseStationBoard);

        $client = $this->createClient();
        $client->request('GET', '/v1/stationboard', $parameters);

        $this->assertEquals($this->getFixture('stationboard/'.$response), $this->json($client->getResponse()));
        $this->assertTrue($client->getResponse()->isOk());
    }
}
