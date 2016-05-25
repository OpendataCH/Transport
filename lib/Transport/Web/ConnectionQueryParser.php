<?php

namespace Transport\Web;

use Symfony\Component\HttpFoundation\Request;
use Transport\Entity\Location\Location;
use Transport\Entity\Schedule\ConnectionQuery;

class ConnectionQueryParser
{
    public static function create(Request $request, Location $from, Location $to, $via = [])
    {
        $datetime = $request->get('datetime');
        if ($datetime) {
            $date = date('Y-m-d', strtotime($datetime));
            $time = date('H:i', strtotime($datetime));
        } else {
            $date = $request->get('date');
            $time = $request->get('time');
        }

        $query = new ConnectionQuery($from, $to, $via, $date, $time);

        $isArrivalTime = $request->get('isArrivalTime');
        if ($isArrivalTime !== null) {
            switch ($isArrivalTime) {
                case 0:
                case 'false':
                    $query->isArrivalTime = false;
                    break;
                case 1:
                case 'true':
                    $query->isArrivalTime = true;
                    break;
                default:
                    //wrong parameter value
                    break;
            }
        }

        $limit = $request->get('limit');
        if ($limit) {
            $query->limit = $limit;
        }

        $page = $request->get('page');
        if ($page) {
            $query->page = $page;
        }

        $transportations = $request->get('transportations');
        if ($transportations) {
            $query->transportations = (array) $transportations;
        }

        $direct = $request->get('direct');
        if ($direct) {
            $query->direct = $direct;
        }

        $sleeper = $request->get('sleeper');
        if ($sleeper) {
            $query->sleeper = $sleeper;
        }

        $couchette = $request->get('couchette', $request->get('chouchette'));
        if ($couchette) {
            $query->couchette = $couchette;
        }

        $bike = $request->get('bike');
        if ($bike) {
            $query->bike = $bike;
        }

        $accessibility = $request->get('accessibility');
        if ($accessibility) {
            $query->accessibility = $accessibility;
        }

        return $query;
    }

    public static function validate(ConnectionQuery $query)
    {
        $errors = [];

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
