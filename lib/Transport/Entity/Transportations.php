<?php

namespace Transport\Entity;

class Transportations
{
    private static $transportationBits = array(
        'all' => 65535, // 1<<16 - 1
        'ice_tgv_rj' => 32768, // 1<<15
        'ec_ic' => 16384, // 1<<14
        'ir' => 8192, // 1<<13
        're_d' => 4096, // 1<<12
        'ship' => 2048, // 1<<11
        's_sn_r' => 1024, // 1<<10
        'bus' => 512, // 1<<9
        'cableway' => 256, // 1<<8
        'arz_ext' => 128, // 1<<7
        'tramway_underground' => 64, // 1<<6
    );

    /**
     * Converts a list of transportation strings into a bitmask accepted by the SBB
     *
     * @param   array[]string   $transportations    A list of transportations
     * @return  string          A binary representation of the transportations given
     */
    public static function reduceTransportations($transportations = array())
    {
        $map = self::$transportationBits;
        return sprintf('%016b', array_reduce($transportations, function ($aggr, $val) use ($map) { return $aggr + $map[$val]; }, 0));
    }

    /**
     * @return array
     */
    public function getTransportations()
    {
        return self::$transportations;
    }
}
