<?php

namespace Transport;

use Predis\Client;
use Transport\Entity\Location\Location;

class Statistics {

    protected $redis;

    public function __construct(Client $redis = null)
    {
        $this->redis = $redis;
    }

    public function call()
    {
        if ($this->redis) {
            $date = date('Y-m-d');
            $key = "stats:calls:$date";
            $this->redis->incr($key);
        }
    }

    public function station(Location $station)
    {
        $this->count('stats:stations', $station->id, array('name' => $station->name, 'x' => $station->coordinate->x, 'y' => $station->coordinate->y));
    }

    public function resource($path)
    {
        $this->count('stats:resources', $path, array('path' => $path));
    }

    protected function count($prefix, $id, $data)
    {
        if ($this->redis) {
            $key = "$prefix:$id";
            $this->redis->hmset($key, $data);
            $this->redis->sadd($prefix, $key);
            $this->redis->hincrby($key, 'calls', 1);
        }
    }

    public function getCalls()
    {
	    $keys = $this->redis->keys('stats:calls:*');
	    $values = $this->redis->mget($keys);
	    $calls = array();
	    foreach ($keys as $i => $key) {
	        $calls[substr($key, 12, 10)] = $values[$i];
	    }
	    ksort($calls);

	    return $calls;
    }

    public function getTopResources()
    {
        return $this->top('stats:resources', array('path', 'calls'));
    }

    public function getTopStations()
    {
        return $this->top('stats:stations', array('name', 'x', 'y', 'calls'));
    }

    protected function top($key, $fields)
    {
        $result = $this->redis->sort($key, array(
            'by' => '*->calls',
            'limit' => array(0, 5),
            'get' => array_map(function ($value) { return "*->$value"; }, $fields),
            'sort'  => 'DESC',
        ));

        // regroup
        $data = array();
        foreach (array_chunk($result, count($fields)) as $values) {
            $data[] = array_combine($fields, $values);
        }

        return $data;
    }
}
