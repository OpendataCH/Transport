<?php

namespace Transport\Entity\Location;

use Transport\Entity\Coordinate;
use Transport\Entity\Transportations;

class NearbyQuery
{
    public $lat;

    public $lon;

    public $limit;

    public $transportations = ['all'];

    public function __construct($lat, $lon, $limit = 10)
    {
        $this->lat = $lat;
        $this->lon = $lon;
        $this->limit = $limit;
    }

    public function toArray()
    {
        return [
            'performLocating' => '2',
            'tpl'             => 'stop2json',
            'look_maxno'      => $this->limit,
            'look_stopclass'  => Transportations::reduceTransportationsDec($this->transportations, 10),
            'look_maxdist'    => 5000,
            'look_y'          => Coordinate::floatToInt($this->lat),
            'look_x'          => Coordinate::floatToInt($this->lon),
        ];
    }
}
