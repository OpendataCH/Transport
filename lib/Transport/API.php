<?php

namespace Transport;

use Buzz\Browser;
use Transport\Entity\Location\Location;
use Transport\Entity\Query;
use Transport\Entity\Location\LocationQuery;
use Transport\Entity\Location\NearbyQuery;
use Transport\Entity\Schedule\ConnectionQuery;
use Transport\Entity\Schedule\StationBoardQuery;

class API
{
    const URL = 'http://xmlfahrplan.sbb.ch/bin/extxml.exe/';
    const URL_QUERY = 'http://fahrplan.sbb.ch/bin/query.exe/dny';

    const SBB_PROD = 'iPhone3.1';
    const SBB_VERSION = '2.3';
    const SBB_ACCESS_ID = 'MJXZ841ZfsmqqmSymWhBPy5dMNoqoGsHInHbWJQ5PTUZOJ1rLTkn8vVZOZDFfSe';

    const DATE_TYPE_DEPARTURE = 0;
    const DATE_TYPE_ARRIVAL = 1;

    const SEARCH_MODE_NORMAL = 'N';
    const SEARCH_MODE_ECONOMIC = 'P';

    /**
     * @var Buzz\Browser
     */
    protected $browser;

    /**
     * @var string
     */
    protected $lang;

    public function __construct(Browser $browser = null, $lang = 'EN') {
        $this->browser = $browser ?: new Browser();
        $this->lang = $lang;
    }

    /**
     * @return Buzz\Message\Response
     */
    public function sendQuery(Query $query) {

        $headers = array();
        $headers[] = 'User-Agent: SBBMobile/4.2 CFNetwork/485.13.9 Darwin/11.0.0';
        $headers[] = 'Accept: application/xml';
        $headers[] = 'Content-Type: application/xml';

        return $this->browser->post(self::URL, $headers, $query->toXml());
    }

    /**
     * @return array
     */
    public function findConnections(ConnectionQuery $query)
    {
        // send request
        $response = $this->sendQuery($query);

        // parse result
        $result = simplexml_load_string($response->getContent());

        $connections = array();
        foreach ($result->ConRes->ConnectionList->Connection as $connection) {

            $connections[] = Entity\Schedule\Connection::createFromXml($connection);
        }

        return $connections;
    }

    /**
     * @return array
     */
    public function findLocations(LocationQuery $query)
    {
        // send request
        $response = $this->sendQuery($query);

        // parse result
        $result = simplexml_load_string($response->getContent());

        $locations = array();
        foreach ($result->LocValRes as $part) {

            $id = (string) $part['id'];

            $locations[$id] = array();
            foreach ($part->children() as $location) {

                $location = Entity\LocationFactory::createFromXml($location);
                if ($location) {
                    $locations[$id][] = $location;
                }
            }
        }

        if (count($locations) > 1) {
            return $locations;
        }
        return reset($locations);
    }

    /**
     * @return array
     */
    public function findNearbyLocations(NearbyQuery $query)
    {
        $url = self::URL_QUERY . '?' . http_build_query($query->toArray());

        // send request
        $response = $this->browser->get($url);

        // fix broken JSON
        $content = $response->getContent();
        $content = preg_replace('/(\w+) ?:/i', '"\1":', $content);
               
        // parse result
        $result = json_decode($content);

        $locations = array();
        foreach ($result->stops as $stop) {

            $location = Entity\LocationFactory::createFromJson($stop);
            if ($location) {
                $locations[] = $location;
            }
        }

        return $locations;
    }

    /**
     * @param Entity\Station $station
     * @param string $boardType
     * @param int $maxJourneys
     * @param string $dateTime
     * @param array $transportationTypes
     */
    public function getStationBoard(StationBoardQuery $query)
    {
        // send request
        $response = $this->sendQuery($query);

        // fix wrong XML encoding information
        $content = $response->getContent();
        $content = str_replace('encoding="iso-8859-1"', 'encoding="UTF-8"', $content);

        // parse result
        $result = simplexml_load_string($content);

        // since the stationboard always lists all connections starting from now we just use the date
        // and wrap it accordingly if time goes over midnight
        $journeys = array();
        $prevTime = strtotime($query->date);
        $date = date('Y-m-d', $prevTime);
        if ($result->STBRes->JourneyList->STBJourney) {
            foreach ($result->STBRes->JourneyList->STBJourney as $journey) {
                $curTime = strtotime((string) $journey->MainStop->BasicStop->Dep->Time);
                if ($prevTime > $curTime) { // we passed midnight
                    $date = date('Y-m-d', strtotime("$date +1day"));
                }
                $journeys[] = Entity\Schedule\StationBoardJourney::createFromXml($journey, $date);
                $prevTime = $curTime;
            }
        }

        return $journeys;
    }
}
