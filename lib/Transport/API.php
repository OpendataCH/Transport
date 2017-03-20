<?php

namespace Transport;

use Buzz\Browser;
use Transport\Entity\Location\Location;
use Transport\Entity\Location\LocationQuery;
use Transport\Entity\Location\NearbyQuery;
use Transport\Entity\Query;
use Transport\Entity\Schedule\Connection;
use Transport\Entity\Schedule\ConnectionPageQuery;
use Transport\Entity\Schedule\ConnectionQuery;
use Transport\Entity\Schedule\Journey;
use Transport\Entity\Schedule\StationBoardQuery;

class API
{
    const URL = 'http://fahrplan.sbb.ch/bin/extxml.exe/';
    const URL_QUERY = 'http://fahrplan.sbb.ch/bin/query.exe/dny';

    const SBB_PROD = 'iPhone3.1';
    const SBB_VERSION = '2.3';
    const SBB_ACCESS_ID = 'vWjygiRIy0uclbLz4qDO7S3G4dcIIViwoLFCZlopGhe88vlsfedGIqctZP9lvqb';

    const SEARCH_MODE_NORMAL = 'N';
    const SEARCH_MODE_ECONOMIC = 'P';

    /**
     * @var \Buzz\Browser
     */
    protected $browser;

    /**
     * @var string
     */
    protected $lang;

    public function __construct(Browser $browser = null, $lang = 'EN')
    {
        $this->browser = $browser ?: new Browser();
        $this->lang = $lang;
    }

    /**
     * @return \SimpleXMLElement
     */
    private function sendAndParseQuery(Query $query)
    {
        $response = $this->sendQuery($query);

        // check for server error
        if ($response->isServerError()) {
            throw new \Exception('Server error from fahrplan.sbb.ch: '.$response->getStatusCode().' '.$response->getReasonPhrase());
        }

        // parse result
        $content = $response->getContent();
        $result = @simplexml_load_string($content);

        // check for XML error
        if ($result === false) {
            throw new \Exception('Invalid XML from fahrplan.sbb.ch: '.$content);
        }

        // check for SBB error
        if ($result->Err) {
            throw new \Exception('Error from fahrplan.sbb.ch: '.$result->Err['code'].' - '.$result->Err['text']);
        }

        return $result;
    }

    /**
     * @return \Buzz\Message\Response
     */
    public function sendQuery(Query $query, $url = self::URL)
    {
        $headers = [];
        $headers[] = 'User-Agent: SBBMobile/4.8 CFNetwork/609.1.4 Darwin/13.0.0';
        $headers[] = 'Accept: application/xml';
        $headers[] = 'Content-Type: application/xml';

        return $this->browser->post($url, $headers, $query->toXml());
    }

    /**
     * @return Connection[]
     */
    public function findConnections(ConnectionQuery $query)
    {
        // send request
        $result = $this->sendAndParseQuery($query);

        // load pages
        for ($i = 0; $i < abs($query->page); $i++) {

            // load next page
            $pageQuery = new ConnectionPageQuery($query, (string) $result->ConRes->ConResCtxt);

            $result = $this->sendAndParseQuery($pageQuery);
        }

        $connections = [];
        if ($result->ConRes->ConnectionList->Connection) {
            foreach ($result->ConRes->ConnectionList->Connection as $connection) {
                $connections[] = Entity\Schedule\Connection::createFromXml($connection, null);
            }
        }

        return $connections;
    }

    /**
     * @return Location[]
     */
    public function findLocations(LocationQuery $query)
    {
        // send request
        $result = $this->sendAndParseQuery($query);

        $locations = [];
        $viaCount = 0;
        foreach ($result->LocValRes as $part) {
            $id = (string) $part['id'];

            // A "via" can occur 0-5 times
            if ($id == 'via') {
                $id = $id.(++$viaCount);
            }

            $locations[$id] = [];
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
     * @return Location[]
     */
    public function findNearbyLocations(NearbyQuery $query)
    {
        $url = self::URL_QUERY.'?'.http_build_query($query->toArray());

        // send request
        $response = $this->browser->get($url);

        // check for server error
        if ($response->isServerError()) {
            throw new \Exception('Server error from fahrplan.sbb.ch: '.$response->getStatusCode().' '.$response->getReasonPhrase());
        }

        // fix broken JSON
        $content = $response->getContent();
        $content = preg_replace('/(\w+) ?:/i', '"\1":', $content);
        $content = str_replace("\\'", "'", $content);

        // parse result
        $result = json_decode($content);

        // check for JSON error
        if ($result === null) {
            throw new \Exception('Invalid JSON from fahrplan.sbb.ch: '.$content);
        }

        $locations = [];
        foreach ($result->stops as $stop) {
            $location = Entity\LocationFactory::createFromJson($stop);
            if ($location) {
                $location->distance = $location->coordinate->getDistanceTo($query->lat, $query->lon);
                $locations[] = $location;
            }
        }

        return $locations;
    }

    /**
     * @return Journey[]
     */
    public function getStationBoard(StationBoardQuery $query)
    {
        // send request
        $result = $this->sendAndParseQuery($query);

        $date = $query->date;

        $journeys = [];
        if ($result->STBRes->JourneyList->STBJourney) {
            foreach ($result->STBRes->JourneyList->STBJourney as $journey) {
                $journey = Entity\Schedule\StationBoardJourney::createStationBoardFromXml($journey, $date, null);

                $date = new \DateTime($journey->stop->departure);

                $journeys[] = $journey;
            }
        }

        return $journeys;
    }
}
