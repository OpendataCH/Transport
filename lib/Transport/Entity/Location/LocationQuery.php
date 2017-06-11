<?php

namespace Transport\Entity\Location;

use Buzz\Message\Form\FormRequest;
use Transport\Entity\Query;

class LocationQuery extends Query
{
    const SBB_SEARCH_MODE = '1';

    private static $locationTypes = [
        'all'     => 'ALLTYPE',
        'station' => 'ST',
        'address' => 'ADR',
        'poi'     => 'POI',
    ];

    /**
     * @var array
     */
    public $query;

    public $type;

    public $lat;

    public $lon;

    /**
     * Finds all stations, locations and poi matching the search query.
     *
     * @param string|array $query Search query (e.g. Ber)
     * @param string       $type  Location types to return (all, station, address, poi)
     */
    public function __construct($query, $type = null, $lat = null, $lon = null)
    {
        $this->query = $query;
        $this->type = $type;
        $this->lat = $lat;
        $this->lon = $lon;
    }

    public function toFormRequest()
    {
        $request = new FormRequest(FormRequest::METHOD_GET, \Transport\API::URL . 'completion.json');
        $request->setField('term', $this->query);

        if ($this->lat && $this->lon) {
            $request->setField('latlon', $this->lat . ',' . $this->lon);
        }

        $request->setField('show_ids', '1');
        $request->setField('show_coordinates', '1');

        return $request;
    }

    public function toXml()
    {
        $request = $this->createRequest();

        foreach ($this->query as $key => $value) {

            // If the key is "via", this is a subarray.
            if ($key === 'via') {
                $queryArray = [];
                foreach ($value as $k => $v) {
                    $queryArray[$key.($k + 1)] = $v;
                }
            } else {
                $queryArray = [$key => $value];
            }

            foreach ($queryArray as $k => $v) {
                $local = $request->addChild('LocValReq');
                $local['id'] = preg_match('/^via[0-9]+$/', $k) ? 'via' : $k;
                $local['sMode'] = self::SBB_SEARCH_MODE;

                $location = $local->addChild('ReqLoc');
                $location['match'] = $v;

                if (!isset(self::$locationTypes[$this->type])) {
                    $this->type = 'all'; // default type
                }
                $location['type'] = self::$locationTypes[$this->type];
            }
        }

        return $request->asXML();
    }

    /**
     * @return array
     */
    public function getLocationTypes()
    {
        return self::$locationTypes;
    }
}
