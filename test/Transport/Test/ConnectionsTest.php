<?php

namespace Transport\Test;

use Buzz\Message\Response;

class ConnectionsTest extends IntegrationTest
{
    public function testGetConnections()
    {
        $responseLocation = new Response();
        $responseLocation->setContent($this->getFixture('location.xml'));

        $responseConnection = new Response();
        $responseConnection->setContent($this->getFixture('archive/connection-2012-01-31.xml'));

        $this->getBrowser()->expects($this->any())
            ->method('post')
            ->will($this->onConsecutiveCalls($responseLocation, $responseConnection));

        $client = $this->createClient();
        $crawler = $client->request('GET', '/v1/connections', array(
            'from' => 'Bern',
            'to' => 'Zürich',
            'date' => '2012-01-31',
            'time' => '23:55:00',
        ));

        $this->assertEquals($this->getFixture('connections/response_connection-2012-01-31.json'), $this->json($client->getResponse()));
        $this->assertTrue($client->getResponse()->isOk());
    }
}
