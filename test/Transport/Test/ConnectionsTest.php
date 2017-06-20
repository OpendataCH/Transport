<?php

namespace Transport\Test;

use Buzz\Message\Response;

class ConnectionsTest extends IntegrationTest
{
    public function connectionsProvider()
    {
        return [
            [['from' => 'Zürich', 'to' => 'Bern', 'date' => '2016-12-23', 'time' => '14:30:00'], 'searchch_response_2016-12-23.json', 'response_2016-12-23.json'],
            [['from' => 'Zürich HB', 'to' => 'Olten', 'date' => '2017-06-20', 'time' => '22:30:00'], 'searchch_response_2017-06-20.json', 'response_2017-06-20.json'],
        ];
    }

    /**
     * @dataProvider connectionsProvider
     */
    public function testGetConnections($parameters, $hafasResponse, $response)
    {
        $responseConnection = new Response();
        $responseConnection->setContent($this->getFixture('connections/'.$hafasResponse));

        $this->getBrowser()->expects($this->any())
            ->method('send')
            ->willReturn($responseConnection);

        $client = $this->createClient();
        $client->request('GET', '/v1/connections', $parameters);

        $this->assertEquals($this->getFixture('connections/'.$response), $this->json($client->getResponse()));
        $this->assertTrue($client->getResponse()->isOk());
    }

    public function testFindConnectionsError()
    {
        $response = new Response();
        $response->setContent($this->getFixture('connections/searchch_response_error.json'));

        $this->browser->expects($this->once())
            ->method('send')
            ->will($this->returnValue($response));

        $client = $this->createClient();
        $client->request('GET', '/v1/connections', ['from' => 'Zürich', 'to' => 'Bern']);

        $this->assertEquals($this->getFixture('connections/response_error.json'), $this->json($client->getResponse()));
        $this->assertEquals(500, $client->getResponse()->getStatusCode());
    }

    public function testFindConnections500()
    {
        $response = new Response();
        $response->setContent($this->getFixture('connections/searchch_response_500.json'));

        $this->browser->expects($this->once())
            ->method('send')
            ->will($this->returnValue($response));

        $client = $this->createClient();
        $client->request('GET', '/v1/connections', ['from' => 'Zürich', 'to' => 'Bern']);

        $this->assertEquals($this->getFixture('connections/response_500.json'), $this->json($client->getResponse()));
        $this->assertEquals(500, $client->getResponse()->getStatusCode());
    }
}
