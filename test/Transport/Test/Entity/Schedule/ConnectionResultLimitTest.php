<?php

namespace Transport\Test\Entity\Schedule;

use Transport\Entity;
use Transport\Entity\Schedule\Connection;

use Transport\ResultLimit;

class ConnectionResultLimitTest extends \PHPUnit_Framework_TestCase
{
    protected function getConnection()
    {
        $from = new Entity\Schedule\Stop();
        $station = new Entity\Location\Station();
            $station->name = "Zürich HB";
            $station->id = "008503000";
            $coordinates = new Entity\Coordinate();
                $coordinates->x = 8.540192;
                $coordinates->y = 47.378177;
                $coordinates->type = "WGS84";
            $station->coordinate = $coordinates;
        $from->station = $station;

        $to = new Entity\Schedule\Stop();
        $to->arrival = '2012-01-31T19:42:00+0100';
        $connection = new Entity\Schedule\Connection();
        $connection->from = $from;
        $connection->to = $to;
        $connection->sections = null;

        return $connection;
    }

    public function testCreateFromXml()
    {
        $xml = simplexml_load_file(__DIR__ . '/../../../../fixtures/connection.xml');
        ResultLimit::setFields(array('connections/from/station','connections/to/arrival'));
        $this->assertEquals($this->getConnection(), Connection::createFromXml($xml->ConRes->ConnectionList->Connection, null, 'connections'));
    }
}

