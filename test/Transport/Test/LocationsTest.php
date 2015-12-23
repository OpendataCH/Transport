<?php

namespace Transport\Test;

use Buzz\Message\Response;

class LocationsTest extends IntegrationTest
{
    public function testGetLocation()
    {
        $response = new Response();
        $response->setContent($this->getFixture('locations/hafas_response.xml'));

        $this->getBrowser()->expects($this->any())
            ->method('post')
            ->withConsecutive(
                array($this->anything(), $this->anything(), $this->equalTo($this->getXmlFixture('locations/hafas_request.xml')))
            )
            ->will($this->onConsecutiveCalls($response));

        $client = $this->createClient();
        $crawler = $client->request('GET', '/v1/locations', array(
            'query' => 'Be',
        ));

        $this->assertEquals($this->getFixture('locations/response.json'), $this->json($client->getResponse()));
        $this->assertTrue($client->getResponse()->isOk());
    }

    public function testGetNearbyLocation()
    {
        $response = new Response();
        $response->setContent($this->getFixture('locations/hafas_response_nearby.json'));

        $this->getBrowser()->expects($this->any())
            ->method('get')
            ->withConsecutive(
                array('http://fahrplan.sbb.ch/bin/query.exe/dny?performLocating=2&tpl=stop2json&look_maxno=10&look_stopclass=1023&look_maxdist=5000&look_y=47002347&look_x=8379934')
            )
            ->will($this->onConsecutiveCalls($response));

        $client = $this->createClient();
        $crawler = $client->request('GET', '/v1/locations', array(
            'x' => '47.002347',
            'y' => '8.379934',
        ));

        $this->assertEquals($this->getFixture('locations/response_nearby.json'), $this->json($client->getResponse()));
        $this->assertTrue($client->getResponse()->isOk());
    }
}
