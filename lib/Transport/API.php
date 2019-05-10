<?php

namespace Transport;

use Buzz\Browser;
use Symfony\Component\HttpKernel\Exception\HttpException;
use Transport\Entity\Location\LocationQuery;
use Transport\Entity\Location\Station;
use Transport\Entity\Query;
use Transport\Entity\Schedule\ConnectionQuery;
use Transport\Entity\Schedule\StationBoardQuery;

class API
{
    const URL = 'https://timetable.search.ch/api/';

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

    protected $clientIpAddress;

    protected $clientUserAgent;

    public function __construct(Browser $browser = null, $lang = 'EN')
    {
        $this->browser = $browser ?: new Browser();
        $this->lang = $lang;
    }

    public function setClientIpAddress($clientIpAddress)
    {
        $this->clientIpAddress = $clientIpAddress;
    }

    public function setClientUserAgent($clientUserAgent)
    {
        $this->clientUserAgent = $clientUserAgent;
    }

    /**
     * @return object
     */
    private function sendAndParseQuery(Query $query)
    {
        $response = $this->sendQuery($query);

        // check for server error
        if ($response->isServerError()) {
            throw new \Exception('Server error from timetable.search.ch: '.$response->getStatusCode().' '.$response->getReasonPhrase());
        }

        // parse result
        $content = $response->getContent();
        $result = json_decode($content);

        // check for rate limit error
        if ($response->getStatusCode() == 429) {
            throw new HttpException(429, 'Rate limit error from timetable.search.ch: '.$content);
        }

        // check for JSON error
        if ($result === null) {
            throw new \Exception('Invalid JSON from timetable.search.ch: '.$content);
        }

        // check for API error
        if (isset($result->error)) {
            throw new \Exception('Error from timetable.search.ch: '.$result->error);
        }

        return $result;
    }

    /**
     * @return \Buzz\Message\Response
     */
    public function sendQuery(Query $query, $url = self::URL)
    {
        $formRequest = $query->toFormRequest();
        $formRequest->setField('ip_address', $this->clientIpAddress);
        $formRequest->setField('user_agent', $this->clientUserAgent);

        return $this->browser->send($formRequest);
    }

    /**
     * @return array
     */
    public function findConnections(ConnectionQuery $query)
    {
        // send request
        $result = $this->sendAndParseQuery($query);

        $connections = [];
        if (isset($result->connections)) {
            if ($result->connections) {
                foreach ($result->connections as $connection) {
                    $connections[] = Entity\Schedule\Connection::createFromJson($connection, null);
                }
            }
        }

        $max = 16 - $query->limit;
        $min = 0;
        $page = $query->page;
        if ($query->isArrivalTime) {
            // offset page by one for arrival time
            $page = $page - 1;
        }
        $connections = array_slice($connections, min(max($page * $query->limit, $min), $max), $query->limit);

        $from = null;
        $to = null;
        $stations = [
            'from' => [],
            'to'   => [],
        ];
        if (isset($result->points)) {
            $from = Entity\LocationFactory::createFromJson($result->points[0]);
            $stations['from'][] = $from;
            $to = Entity\LocationFactory::createFromJson($result->points[1]);
            $stations['to'][] = $to;
        }

        $result = [
            'connections' => $connections,
            'from'        => $from,
            'to'          => $to,
            'stations'    => $stations,
        ];

        return $result;
    }

    /**
     * @return array
     */
    public function findLocations(LocationQuery $query)
    {
        // send request
        $result = $this->sendAndParseQuery($query);

        $locations = [];
        foreach ($result as $location) {
            $locations[] = Entity\LocationFactory::createFromJson($location);
        }

        return $locations;
    }

    /**
     * @return array
     */
    public function getStationBoard(StationBoardQuery $query)
    {
        // send request
        $result = $this->sendAndParseQuery($query);

        $station = Station::createStationFromJson($result->stop);

        $journeys = [];

        if ($result->connections) {
            foreach ($result->connections as $connection) {
                $journey = Entity\Schedule\StationBoardJourney::createFromJson($connection, null);
                $journey->stop->station = $station;
                $journeys[] = $journey;
            }
        }

        $stationboard = ['station' => $station, 'stationboard' => $journeys];

        return $stationboard;
    }
}
