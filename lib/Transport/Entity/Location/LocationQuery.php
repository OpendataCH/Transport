<?php 

namespace Transport\Entity\Location;

use Transport\Entity\Query;
use Transport\Entity\Transportations;
use Transport\Entity\Location\Location;

class LocationQuery extends Query
{
    const SBB_SEARCH_MODE = '1';

    private static $locationTypes = array(
        'all' => 'ALLTYPE',
        'station' => 'ST',
        'address' => 'ADR',
        'poi' => 'POI',
    );

    /**
     * @var array
     */
    public $query;

    public $type;

    /**
     * Finds all stations, locations and poi matching the search query.
     *
     * @param string|array $query Search query (e.g. Ber)
     * @param string $type  Location types to return (all, station, address, poi)
     */
    public function __construct($query, $type = null) {

        // convert query to array
        if (!is_array($query)) {
            $query = array($query);
        }
        $this->query = $query;

        $this->type = $type;
    }

    public function toXml() {

        $request = $this->createRequest();

        foreach ($this->query as $key => $value) {

            $local = $request->addChild('LocValReq');
            $local['id'] = $key;
            $local['sMode'] = self::SBB_SEARCH_MODE;

            $location = $local->addChild('ReqLoc');
            $location['match'] = $value;

            if (!isset(self::$locationTypes[$this->type])) {
                $this->type = 'all'; // default type
            }
            $location['type'] = self::$locationTypes[$this->type];
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
