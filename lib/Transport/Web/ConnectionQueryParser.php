<?php

namespace Transport\Web;

use Symfony\Component\HttpFoundation\Request;

use Transport\Entity\Schedule\ConnectionQuery;
use Transport\Entity\Location\Location;

class ConnectionQueryParser
{
    public static function create(Request $request, Location $from, Location $to, $via = array())
    {
        $date = $request->get('date') ?: null;
        $time = $request->get('time') ?: null;

        $query = new ConnectionQuery($from, $to, $via, $date, $time);

        $isArrivalTime = $request->get('isArrivalTime') ?: null;
        if ($isArrivalTime !== null) {
            switch ($isArrivalTime) {
                case 0:
                case "false":
                    $query->isArrivalTime = false;
                    break;
                case 1:
                case "true":
                    $query->isArrivalTime = true;
                    break;
                default:
                    //wrong parameter value
                    break;
            }
        }

        $limit = $request->get('limit') ?: null;
        if ($limit) {
            $query->limit = $limit;
        }

        $page = $request->get('page') ?: null;
        if ($page) {
            $query->page = $page;
        }

        $transportations = $request->get('transportations');
        if ($transportations) {
            $query->transportations = $transportations;
        }

        $direct = $request->get('direct');
        if ($direct) {
            $query->direct = $direct;
        }

        $sleeper = $request->get('sleeper');
        if ($sleeper) {
            $query->sleeper = $sleeper;
        }

        $couchette = $request->get('chouchette');
        if ($couchette) {
            $query->couchette = $couchette;
        }

        $bike = $request->get('bike');
        if ($bike) {
            $query->bike = $bike;
        }

        return $query;
    }

    public static function validate(ConnectionQuery $query)
    {
        $errors = array();

        if ($query->limit > 6) {
            $errors[] = 'Maximal value of argument `limit` is 6.';
        }
        if ($query->page > 10) {
            $errors[] = 'Maximal value of argument `page` is 10.';
        }
        if (count($query->viaLocations) > 5) {
            $errors[] = 'Invalid via count (max 5 allowed).';
        }

        return $errors;
    }
}
