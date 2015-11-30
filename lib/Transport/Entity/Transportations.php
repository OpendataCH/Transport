<?php

namespace Transport\Entity;

class Transportations
{
    private static $transportationBits = array(
        'ice_tgv_rj' => 1, // 2^0
        'ec_ic' => 2, // 2^1
        'ir' => 4, // 2^2
        're_d' => 8, // 2^3
        'ship' => 16, // 2^4
        's_sn_r' => 32, // 2^5
        'bus' => 64, // 2^6
        'cableway' => 128, // 2^7
        'arz_ext' => 256, // 2^8
        'tramway_underground' => 512, // 2^9
        'tramway' => 1024, // 2^10
        'direct' => 2048, // 2^11
        'direct_sleeper' => 4096, // 2^12
        'direct_couchette' => 8192, // 2^13
        'bike' => 16384, // 2^14
        'groups' => 32768, // 2^15
    );

    /**
     * Converts a list of transportation strings into a bitmask accepted by the SBB
     *
     * @param   array[]string   $transportations    A list of transportations
     * @param   int             $limit              Maximum number of transportations (bits)
     * @param   boolean         $lsb0               Least significant bit first, LSB 0
     * @return  string          A binary representation of the transportations given
     */
    public static function reduceTransportations($transportations = array(), $limit = 16, $lsb0 = true)
    {
        $dec = self::reduceTransportationsDec($transportations, $limit);

        $binary = sprintf('%0' . $limit . 'b', $dec);

        if ($lsb0) {
            // flip for SBB
            $binary = strrev($binary);
        }

        return $binary;
    }

    public static function reduceTransportationsDec($transportations = array(), $limit = 16)
    {
        $dec = 0;

        if (in_array('all', $transportations)) {

            $dec = pow(2, $limit) - 1;

        } else {

            $map = self::$transportationBits;
            $dec = array_reduce($transportations, function ($aggr, $val) use ($map) { return $aggr + $map[$val]; }, 0);

        }

        return $dec;
    }
}
