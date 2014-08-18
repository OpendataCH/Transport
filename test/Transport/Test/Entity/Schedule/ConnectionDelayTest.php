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
        $from->departureTimestamp = 1326726600;
        $from->delay = '8';
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
        $from->location = $station;

        $to = new Entity\Schedule\Stop();
        $to->arrival = '2012-01-16T16:49:00+0100';
        $to->arrivalTimestamp = 1326728940;
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
        $to->location = $station;


        $sectionWalk = new Entity\Schedule\Walk();
        $sectionWalk->duration = '00:04:00';

        $sectionFrom = new Entity\Schedule\Stop();
        $sectionFrom->departure = '2012-01-16T16:06:00+0100';
        $sectionFrom->departureTimestamp = 1326726360;
        $station = new Entity\Location\Station();
            $station->name = "Zürich, Bahnhof Altstetten";
            $station->id = "000103022";
            $coordinates = new Entity\Coordinate();
                $coordinates->x = 8.488378;
                $coordinates->y = 47.391103;
                $coordinates->type = "WGS84";
            $station->coordinate = $coordinates;
        $sectionFrom->station = $station;
        $sectionFrom->location = $station;

        $sectionTo = new Entity\Schedule\Stop();
        $sectionTo->arrival = "2012-01-16T16:10:00+0100";
        $sectionTo->arrivalTimestamp = 1326726600;
        $station = new Entity\Location\Station();
            $station->name = "Zürich Altstetten";
            $station->id = "008503001";
            $coordinates = new Entity\Coordinate();
                $coordinates->x = 8.488936;
                $coordinates->y = 47.391481;
                $coordinates->type = "WGS84";
            $station->coordinate = $coordinates;
        $sectionTo->station = $station;
        $sectionTo->location = $station;

        $section1 = new Entity\Schedule\Section();
        $section1->walk = $sectionWalk;
        $section1->departure = $sectionFrom;
        $section1->arrival = $sectionTo;

        $sectionJourney = new Entity\Schedule\Journey();
        $sectionJourney->name = 'S9 18962';
        $sectionJourney->category = 'S9';
        $sectionJourney->categoryCode = 5;
        $sectionJourney->number = '18962';
        $sectionJourney->capacity1st = 1;
        $sectionJourney->capacity2nd = 1;

        $sectionFrom = new Entity\Schedule\Stop();
        $sectionFrom->departure = '2012-01-16T16:10:00+0100';
        $sectionFrom->departureTimestamp = 1326726600;
        $sectionFrom->delay = '8';
        $sectionFrom->platform = '3';
        $prognosis = new Entity\Schedule\Prognosis();
            $prognosis->departure = '2012-01-16T16:18:00+0100';
            $prognosis->capacity1st = '1';
            $prognosis->capacity2nd = '1';
        $sectionFrom->prognosis = $prognosis;
        $station = new Entity\Location\Station();
            $station->name = "Zürich Altstetten";
            $station->id = "008503001";
            $coordinates = new Entity\Coordinate();
                $coordinates->x = 8.488936;
                $coordinates->y = 47.391481;
                $coordinates->type = "WGS84";
            $station->coordinate = $coordinates;
        $sectionFrom->station = $station;
        $sectionFrom->location = $station;

        $sectionTo = new Entity\Schedule\Stop();
        $sectionTo->arrival = '2012-01-16T16:49:00+0100';
        $sectionTo->arrivalTimestamp = 1326728940;
        $sectionTo->platform = '7';
        $station = new Entity\Location\Station();
            $station->name = "Zug";
            $station->id = "008502204";
            $coordinates = new Entity\Coordinate();
                $coordinates->x = 8.515292;
                $coordinates->y = 47.173618;
                $coordinates->type = "WGS84";
            $station->coordinate = $coordinates;
        $sectionTo->station = $station;
        $sectionTo->location = $station;

        $passList = array();
        $passList[0] = clone $sectionFrom;
        $passList[0]->platform = '';
        $passList[1] = clone $sectionTo;
        $passList[1]->platform = '';
        $sectionJourney->passList = $passList;

        $section2 = new Entity\Schedule\Section();
        $section2->journey = $sectionJourney;
        $section2->departure = $sectionFrom;
        $section2->arrival = $sectionTo;

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
            $section1,
            $section2,
        );

        return $connection;
    }

    public function testCreateFromXml()
    {
        $xml = simplexml_load_file(__DIR__ . '/../../../../fixtures/archive/connection-2012-01-16.xml');

        $this->assertEquals($this->getConnection(), Connection::createFromXml($xml->ConRes->ConnectionList->Connection));
    }
}

