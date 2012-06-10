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
            $prognosis->departure = '2012-01-16T16:18:00+0100';
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


        $section1Walk = new Entity\Schedule\Walk();
        $section1Walk->duration = '00:04:00';

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

        $section2Journey = new Entity\Schedule\Journey();
        $section2Journey->name = 'S9 18962';
        $section2Journey->category = 'S9';
        $section2Journey->number = '18962';

        $section2From = new Entity\Schedule\Stop();
        $section2From->departure = '2012-01-16T16:10:00+0100';
        $section2From->platform = '3';
        $prognosis = new Entity\Schedule\Prognosis();
            $prognosis->departure = '2012-01-16T16:18:00+0100';
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
        
        $passList = array();
        $passList[0] = clone $section2From;
        $passList[0]->platform = '';
        $passList[1] = clone $section2To;
        $passList[1]->platform = '';
        $section2Journey->passList = $passList;
        
		$service = new Entity\Schedule\Service();
		$service->regular = 'daily';
		$service->irregular = 'not 28., 29. Jan 2012, 23., 24. Jun 2012';

        $connection = new Entity\Schedule\Connection();
        $connection->from = $from;
        $connection->to = $to;
        $connection->duration = '00d00:43:00';
        $connection->transfers = 0;
        $connection->service = $service;
        $connection->products = array('S9');
        $connection->capacity1st = 1;
        $connection->capacity2nd = 1;
        $connection->sections = array(
            array('walk' => $section1Walk, 'departure' => $section1From, 'arrival' => $section1To),
            array('journey' => $section2Journey, 'departure' => $section2From, 'arrival' => $section2To)
        );

        return $connection;
    }

    public function testCreateFromXml()
    {
        $xml = simplexml_load_file(__DIR__ . '/../../../../fixtures/archive/connection-2012-01-16.xml');

        $this->assertEquals($this->getConnection(), Connection::createFromXml($xml->ConRes->ConnectionList->Connection));
    }
}

