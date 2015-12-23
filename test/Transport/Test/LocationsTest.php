<?php

namespace Transport\Test;

use Buzz\Message\Response;

class LocationsTest extends IntegrationTest
{
    private $url = 'http://fahrplan.sbb.ch/bin/extxml.exe/';

    private $headers = array(
        'User-Agent: SBBMobile/4.8 CFNetwork/609.1.4 Darwin/13.0.0',
        'Accept: application/xml',
        'Content-Type: application/xml'
    );

    public function testGetLocation()
    {
        $response = new Response();
        $response->setContent($this->getFixture('locations/hafas_response.xml'));

        $this->getBrowser()->expects($this->any())
            ->method('post')
            ->withConsecutive(
                array($this->equalTo($this->url), $this->equalTo($this->headers), $this->equalTo($this->getXmlFixture('locations/hafas_request.xml')))
            )
            ->will($this->onConsecutiveCalls($response));

        $client = $this->createClient();
        $crawler = $client->request('GET', '/v1/locations', array(
            'query' => 'Be',
        ));

        $this->assertEquals($this->getFixture('locations/response.json'), $this->json($client->getResponse()));
        $this->assertTrue($client->getResponse()->isOk());
    }

    public function nearbyProvider()
    {
        return array(
            array(array('x' => '47.002347', 'y' => '8.379934'), 'http://fahrplan.sbb.ch/bin/query.exe/dny?performLocating=2&tpl=stop2json&look_maxno=10&look_stopclass=1023&look_maxdist=5000&look_y=47002347&look_x=8379934', 'hafas_response_nearby.json', 'response_nearby.json'),
            array(array('x' => '46.388653', 'y' => '6.238729'), 'http://fahrplan.sbb.ch/bin/query.exe/dny?performLocating=2&tpl=stop2json&look_maxno=10&look_stopclass=1023&look_maxdist=5000&look_y=46388653&look_x=6238729', 'hafas_response_nyon.json', 'response_nyon.json'),
        );
    }

    /**
     * @dataProvider nearbyProvider
     */
    public function testGetNearbyLocation($parameters, $requestUrl, $hafasResponse, $jsonReponse)
    {
        $response = new Response();
        $response->setContent($this->getFixture('locations/' . $hafasResponse));

        $this->getBrowser()->expects($this->any())
            ->method('get')
            ->withConsecutive(
                array($requestUrl)
            )
            ->will($this->onConsecutiveCalls($response));

        $client = $this->createClient();
        $crawler = $client->request('GET', '/v1/locations', $parameters);

        $this->assertEquals($this->getFixture('locations/' . $jsonReponse), $this->json($client->getResponse()));
        $this->assertTrue($client->getResponse()->isOk());
    }
}
