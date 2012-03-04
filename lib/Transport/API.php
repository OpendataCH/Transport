<?php

namespace Transport;

use Buzz\Browser;
use Transport\Entity\Location\Location;
use Transport\Entity\Query;
use Transport\Entity\Location\LocationQuery;
use Transport\Entity\Schedule\ConnectionQuery;
use Transport\Entity\Schedule\StationBoardQuery;

class API
{
    const URL = 'http://xmlfahrplan.sbb.ch/bin/extxml.exe/';

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
        //header('Content-Type: application/xml');
        //echo $response->getContent();exit;

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
                $locations[$id][] = Entity\LocationFactory::createFromXml($location);
            }
        }

        if (count($locations) > 1) {
            return $locations;
        }
        return reset($locations);
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

        // parse result
        $result = simplexml_load_string($response->getContent());

        $journeys = array();
        if ($result->STBRes->JourneyList->STBJourney) {
            foreach ($result->STBRes->JourneyList->STBJourney as $journey) {

                $journeys[] = Entity\Schedule\StationBoardJourney::createFromXml($journey);
            }
        }

        return $journeys;
    }
}
