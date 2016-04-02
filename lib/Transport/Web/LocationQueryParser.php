<?php

namespace Transport\Web;

use Symfony\Component\HttpFoundation\Request;
use Transport\Entity\Location\LocationQuery;

class LocationQueryParser
{
    public static function create(Request $request)
    {
        $from = $request->get('from');
        $to = $request->get('to');

        $via = $request->get('via');
        if (!is_array($via)) {
            if ($via) {
                $via = array($via);
            } else {
                $via = array();
            }
        }

        $query = new LocationQuery(array('from' => $from, 'to' => $to, 'via' => $via));

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
