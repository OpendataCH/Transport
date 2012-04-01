<?php

namespace Transport\Test\Entity\Schedule;

use Transport\Entity;
use Transport\Entity\Schedule\Connection;

class ConnectionDelayTest extends \PHPUnit_Framework_TestCase
{
    protected function getConnection()
    {   
        $from = new Entity\Schedule\Stop();
        $from->departure = '2012-01-16T16:10:00+0100';
        $from->platform = '3';
        $prognosis = new Entity\Schedule\Prognosis();
            $prognosis->time = '8';
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
        $to->arrival = '2012-01-16T16:49:00+0100';
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


        $section1From = new Entity\Schedule\Stop();
        $section1From->departure = '2012-01-16T16:06:00+0100';
        $station = new Entity\Location\Station();
            $station->name = "Zürich, Bahnhof Altstetten";
            $station->id = "000103022";
            $coordinates = new Entity\Coordinate();
                $coordinates->x = 8.488378;
                $coordinates->y = 47.391103;
                $coordinates->type = "WGS84";
            $station->coordinate = $coordinates;
        $section1From->station = $station;

        $section1To = new Entity\Schedule\Stop();
        $section1To->arrival = "2012-01-16T16:10:00+0100";
        $station = new Entity\Location\Station();
            $station->name = "Zürich Altstetten";
            $station->id = "008503001";
            $coordinates = new Entity\Coordinate();
                $coordinates->x = 8.488936;
                $coordinates->y = 47.391481;
                $coordinates->type = "WGS84";
            $station->coordinate = $coordinates;
        $section1To->station = $station;

        $section2From = new Entity\Schedule\Stop();
        $section2From->departure = '2012-01-16T16:10:00+0100';
        $section2From->platform = '3';
        $prognosis = new Entity\Schedule\Prognosis();
            $prognosis->time = '8';
            $prognosis->capacity1st = '1';
            $prognosis->capacity2nd = '1';
        $section2From->prognosis = $prognosis;
        $station = new Entity\Location\Station();
            $station->name = "Zürich Altstetten";
            $station->id = "008503001";
            $coordinates = new Entity\Coordinate();
                $coordinates->x = 8.488936;
                $coordinates->y = 47.391481;
                $coordinates->type = "WGS84";
            $station->coordinate = $coordinates;
        $section2From->station = $station;

        $section2To = new Entity\Schedule\Stop();
        $section2To->arrival = '2012-01-16T16:49:00+0100';
        $section2To->platform = '7';
        $station = new Entity\Location\Station();
            $station->name = "Zug";
            $station->id = "008502204";
            $coordinates = new Entity\Coordinate();
                $coordinates->x = 8.515292;
                $coordinates->y = 47.173618;
                $coordinates->type = "WGS84";
            $station->coordinate = $coordinates;
        $section2To->station = $station;

        
        $connection = new Entity\Schedule\Connection();
        $connection->from = $from;
        $connection->to = $to;
        $connection->sections = array(
            array('departure' => $section1From, 'arrival' => $section1To),
            array('departure' => $section2From, 'arrival' => $section2To)
        );

        return $connection;
    }

    public function testCreateFromXml()
    {
        $xml = simplexml_load_file(__DIR__ . '/../../../../fixtures/archive/connection-2012-01-16.xml');

        $this->assertEquals($this->getConnection(), Connection::createFromXml($xml->ConRes->ConnectionList->Connection));
    }
}

