<?php

namespace Transport\Test\Entity\Schedule;

use Transport\Entity;
use Transport\Entity\Schedule\StationBoardJourney;

class StationBoardJourneyTest extends \PHPUnit_Framework_TestCase
{
    protected function getJourney()
    {   
        $stop = new Entity\Schedule\Stop();
        $stop->departure = '2012-03-31T23:57:00+0200';
        $stop->departureTimestamp = 1333231020;
        $prognosis = new Entity\Schedule\Prognosis();
        $prognosis->capacity1st = '-1';
        $prognosis->capacity2nd = '-1';
        $stop->prognosis = $prognosis;
        $station = new Entity\Location\Station();
            $station->name = 'ZÃ¼rich, BÃ¤ckeranlage';
            $station->id = '8591052';
            $coordinates = new Entity\Coordinate();
                $coordinates->x = 8.525342;
                $coordinates->y = 47.378473;
                $coordinates->type = 'WGS84';
            $station->coordinate = $coordinates;
        $stop->station = $station;
        $stop->location = $station;
        
        $journey = new Entity\Schedule\StationBoardJourney();
        $journey->stop = $stop;
        $journey->name = 'Bus 31';
        $journey->category = 'Bus';
        $journey->categoryCode = 6;
        $journey->subcategory = 'Nbu';
        $journey->number = '31';
        $journey->operator = 'VBZ';
        $journey->to = 'Schlieren, Zentrum';

        return $journey;
    }

    public function testCreateFromXml()
    {
        $xml = simplexml_load_file(__DIR__ . '/../../../../fixtures/stationboard.xml');

        $date = \DateTime::createFromFormat('Y-m-d', '2012-03-31', new \DateTimeZone('Europe/Zurich'));
        $date->setTimezone(new \DateTimeZone('Europe/Zurich'));
        $date->setTime(0, 0, 0);
        $this->assertEquals($this->getJourney(), StationBoardJourney::createFromXml($xml->STBRes->JourneyList->STBJourney[0], $date));
    }
}

