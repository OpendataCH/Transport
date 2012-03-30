<?php 

namespace Transport\Entity\Location;

class NearbyQuery
{
    public $lat;

    public $lon;

    public $limit;

    public function __construct($lat, $lon, $limit = 10)
    {
        $this->lat = $lat;
        $this->lon = $lon;
        $this->limit = $limit;
    }
    
    public function toArray()
    {
        return array(
            'performLocating' => '2',
            'tpl' => 'stop2json',
            'look_maxno' => $this->limit,
            'look_stopclass' => 1023,
            'look_maxdist' => 5000,
            'look_y' => sprintf('%01.6f', $this->lat) * 1000000,
            'look_x' => sprintf('%01.6f', $this->lon) * 1000000
        );
    }
}
