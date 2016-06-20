<?php

namespace Transport\Test;

use Buzz\Message\Response;

class ConnectionsTest extends IntegrationTest
{
    private $url = 'http://fahrplan.sbb.ch/bin/extxml.exe/';

    private $headers = [
        'User-Agent: SBBMobile/4.8 CFNetwork/609.1.4 Darwin/13.0.0',
        'Accept: application/xml',
        'Content-Type: application/xml',
    ];

    public function connectionsProvider()
    {
        return [
            [['from' => 'Zürich', 'to' => 'Bern', 'date' => '2012-01-31', 'time' => '23:55:00'], 'hafas_request_2012-01-31.xml', 'hafas_response_2012-01-31.xml', 'response_2012-01-31.json'],
            [['from' => 'Zürich', 'to' => 'Bern', 'date' => '2012-12-23', 'time' => '14:30:00'], 'hafas_request_2015-12-23.xml', 'hafas_response_2015-12-23.xml', 'response_2015-12-23.json'],
        ];
    }

    /**
     * @dataProvider connectionsProvider
     */
    public function testGetConnections($parameters, $hafasRequest, $hafasResponse, $response)
    {
        $responseLocation = new Response();
        $responseLocation->setContent($this->getFixture('connections/hafas_response_location.xml'));

        $responseConnection = new Response();
        $responseConnection->setContent($this->getFixture('connections/'.$hafasResponse));

        $this->getBrowser()->expects($this->any())
            ->method('post')
            ->withConsecutive(
                [$this->equalTo($this->url), $this->equalTo($this->headers), $this->equalTo($this->getXmlFixture('connections/hafas_request_location.xml'))],
                [$this->equalTo($this->url), $this->equalTo($this->headers), $this->equalTo($this->getXmlFixture('connections/'.$hafasRequest))]
            )
            ->will($this->onConsecutiveCalls($responseLocation, $responseConnection));

        $client = $this->createClient();
        $client->request('GET', '/v1/connections', $parameters);

        $this->assertEquals($this->getFixture('connections/'.$response), $this->json($client->getResponse()));
        $this->assertTrue($client->getResponse()->isOk());
    }

    public function testFindConnectionsError()
    {
        $response = new Response();
        $response->setContent($this->getFixture('connections/hafas_response_error.xml'));

        $this->browser->expects($this->once())
            ->method('post')
            ->with($this->equalTo($this->url))
            ->will($this->returnValue($response));

        $client = $this->createClient();
        $client->request('GET', '/v1/connections', ['from' => 'Zürich', 'to' => 'Bern']);

        $this->assertEquals($this->getFixture('connections/response_error.json'), $this->json($client->getResponse()));
        $this->assertEquals(500, $client->getResponse()->getStatusCode());
    }

    public function testFindConnections500()
    {
        $response = new Response();
        $response->setContent($this->getFixture('connections/hafas_response_500.xml'));

        $this->browser->expects($this->once())
            ->method('post')
            ->with($this->equalTo($this->url))
            ->will($this->returnValue($response));

        $client = $this->createClient();
        $client->request('GET', '/v1/connections', ['from' => 'Zürich', 'to' => 'Bern']);

        $this->assertEquals($this->getFixture('connections/response_500.json'), $this->json($client->getResponse()));
        $this->assertEquals(500, $client->getResponse()->getStatusCode());
    }
}
