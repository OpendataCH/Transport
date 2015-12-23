<?php

namespace Transport\Test;

use Buzz\Message\Response;
use Transport\Entity\Location\LocationQuery;
use Transport\Entity\Location\NearbyQuery;
use Transport\Entity\Location\Station;
use Transport\Entity\Schedule\ConnectionQuery;

class APITest extends \PHPUnit_Framework_TestCase
{
    protected function setUp()
    {
        $this->browser = $this->getMock('Buzz\\Browser', array('post', 'get'));

        $this->api = new \Transport\API($this->browser);
    }

    /**
     * @expectedException Exception
     * @expectedExceptionMessage Error from fahrplan.sbb.ch: F2 - Spool: Error writing the spoolfile.
     */
    public function testFindConnectionsError()
    {
        $response = new Response();
        $response->setContent(file_get_contents(__DIR__ . '/../../fixtures/hafas_response_error.xml'));

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
        $response->setContent(file_get_contents(__DIR__ . '/../../fixtures/hafas_response_500.xml'));

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
