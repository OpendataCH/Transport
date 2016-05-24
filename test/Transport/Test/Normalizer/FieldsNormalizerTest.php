<?php

namespace Transport\Test\Normalizer;

use Symfony\Component\Serializer\Encoder\JsonEncoder;
use Symfony\Component\Serializer\Serializer;
use Transport\Entity;
use Transport\Normalizer\FieldsNormalizer;

class FieldsNormalizerTest extends \PHPUnit_Framework_TestCase
{
    protected function getConnection()
    {
        $from = new Entity\Schedule\Stop();
        $station = new Entity\Location\Station();
        $station->name = 'Zürich HB';
        $station->id = '008503000';
        $coordinates = new Entity\Coordinate();
        $coordinates->x = 8.540192;
        $coordinates->y = 47.378177;
        $coordinates->type = 'WGS84';
        $station->coordinate = $coordinates;
        $from->station = $station;

        $to = new Entity\Schedule\Stop();
        $to->arrival = '2012-01-31T19:42:00+0100';

        $connection = new Entity\Schedule\Connection();
        $connection->from = $from;
        $connection->to = $to;

        return $connection;
    }

    public static function provider()
    {
        return [
            ['{"from":{"station":{"name":"Z\u00fcrich HB"}},"to":{"arrival":"2012-01-31T19:42:00+0100"}}', ['from/station/name', 'to/arrival']],
            ['{"from":{"station":{"id":"008503000"}}}', ['from/station/id']],
            ['{"from":{"station":{"id":"008503000","name":"Z\u00fcrich HB","score":null,"coordinate":{"type":"WGS84","x":8.540192,"y":47.378177},"distance":null}}}', ['from/station']],
        ];
    }

    /**
     * @dataProvider provider
     */
    public function testSerializeConnection($json, $fields)
    {
        $serializer = new Serializer([new FieldsNormalizer($fields)], ['json' => new JsonEncoder()]);

        $this->assertEquals($json, $serializer->serialize($this->getConnection(), 'json'));
    }
}
