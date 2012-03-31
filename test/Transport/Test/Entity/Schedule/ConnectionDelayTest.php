<?php

namespace Transport\Test\Entity\Schedule;

use Transport\Entity;
use Transport\Entity\Schedule\Connection;

class ConnectionDelayTest extends \PHPUnit_Framework_TestCase
{
    protected function getConnection()
    {   
        $from = new Entity\Schedule\Stop();
        $from->departure = '16:10:00';
        $from->platform = '3';
        $prognosis = new Entity\Schedule\Prognosis();
        $prognosis->time = '16:18:00';
        $prognosis->capacity1st = '1';
        $prognosis->capacity2nd = '1';
        $from->prognosis = $prognosis;
        $station = new Entity\Location\Station();
            $station->name = "Zürich Altstetten";
            $station->id = "008503001";
            $coordinates = new Entity\Coordinate();
                $coordinates->x = 8.488936;
                $coordinates->y = 47.391481;
                $coordinates->type = "WGS84";
            $station->coordinate = $coordinates;
        $from->station = $station;

        $to = new Entity\Schedule\Stop();
        $to->arrival = '16:49:00';
        $to->platform = '7';
        $station = new Entity\Location\Station();
            $station->name = "Zug";
            $station->id = "008502204";
            $coordinates = new Entity\Coordinate();
                $coordinates->x = 8.515292;
                $coordinates->y = 47.173618;
                $coordinates->type = "WGS84";
            $station->coordinate = $coordinates;
        $to->station = $station;
        
        $connection = new Entity\Schedule\Connection();
        $connection->date = '2012-01-16';
        $connection->from = $from;
        $connection->to = $to;

        return $connection;
    }

    public function testCreateFromXml()
    {
        $xml = simplexml_load_file(__DIR__ . '/../../../../fixtures/archive/connection-2012-01-16.xml');

        $this->assertEquals($this->getConnection(), Connection::createFromXml($xml->ConRes->ConnectionList->Connection));
    }
}

