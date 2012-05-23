<?php

namespace Transport\Test\Entity\Schedule;

use Transport\Entity;
use Transport\Entity\Schedule\Connection;

use Transport\ResultLimit;

class ConnectionTest extends \PHPUnit_Framework_TestCase
{
    protected function getConnection()
    {

        $journey = new Entity\Schedule\Journey();
        $journey->name = 'S1219278';
        $journey->category = 'S12';
        $journey->number = '19278';


        $from = new Entity\Schedule\Stop();
        $from->departure = '2012-01-31T19:14:00+0100';
        $from->platform = '21/22';
        $prognosis = new Entity\Schedule\Prognosis();
        $prognosis->capacity1st = '1';
        $prognosis->capacity2nd = '2';
        $from->prognosis = $prognosis;
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
        $to->platform = '3';
        $station = new Entity\Location\Station();
            $station->name = "Baden";
            $station->id = "008503504";
            $coordinates = new Entity\Coordinate();
                $coordinates->x = 8.307695;
                $coordinates->y = 47.47642;
                $coordinates->type = "WGS84";
            $station->coordinate = $coordinates;
        $to->station = $station;
        
        $passList = array();
        $passList[0] = clone $from;
        $passList[0]->platform = '';
        $passList[1] = clone $to;
        $passList[1]->platform = '';
        $journey->passList = $passList;

        $sections[] = array('journey' => $journey, 'departure' => $from, 'arrival' => $to);

        $connection = new Entity\Schedule\Connection();
        $connection->from = $from;
        $connection->to = $to;
        $connection->duration = '00d00:28:00';
        $connection->transfers = 0;
        $connection->serviceDays = array('regularService' => 'daily');
        $connection->products = array('S12');
        $connection->capacity1st = 1;
        $connection->capacity2nd = 2;
        $connection->sections = $sections;

        return $connection;
    }

    public function testCreateFromXml()
    {
        $xml = simplexml_load_file(__DIR__ . '/../../../../fixtures/connection.xml');
        ResultLimit::unsetFields();
        $this->assertEquals($this->getConnection(), Connection::createFromXml($xml->ConRes->ConnectionList->Connection));
    }
}

