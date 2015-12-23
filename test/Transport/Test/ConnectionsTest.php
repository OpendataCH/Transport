<?php

namespace Transport\Test;

use Buzz\Message\Response;

class ConnectionsTest extends IntegrationTest
{
    public function testGetConnections()
    {
        $responseLocation = new Response();
        $responseLocation->setContent($this->getFixture('connections/hafas_response_location.xml'));

        $responseConnection = new Response();
        $responseConnection->setContent($this->getFixture('connections/hafas_response_2012-01-31.xml'));

        $this->getBrowser()->expects($this->any())
            ->method('post')
            ->withConsecutive(
                array($this->anything(), $this->anything(), $this->equalTo($this->getXmlFixture('connections/hafas_request_location.xml'))),
                array($this->anything(), $this->anything(), $this->equalTo($this->getXmlFixture('connections/hafas_request_2012-01-31.xml')))
            )
            ->will($this->onConsecutiveCalls($responseLocation, $responseConnection));

        $client = $this->createClient();
        $crawler = $client->request('GET', '/v1/connections', array(
            'from' => 'Zürich',
            'to' => 'Bern',
            'date' => '2012-01-31',
            'time' => '23:55:00',
        ));

        $this->assertEquals($this->getFixture('connections/response_2012-01-31.json'), $this->json($client->getResponse()));
        $this->assertTrue($client->getResponse()->isOk());
    }
}
