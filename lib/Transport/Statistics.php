<?php

namespace Transport;

use Predis\Client;
use Transport\Entity\Location\Location;
use Transport\Entity\Location\Station;

class Statistics {

    protected $redis;

    protected $enabled;

    public function __construct(Client $redis = null, $enabled = false)
    {
        $this->redis = $redis;
        $this->enabled = $enabled;
    }

    public function call()
    {
        if ($this->enabled) {
            $date = date('Y-m-d');
            $prefix = "stats:calls";
            $key = "$prefix:$date";
            $this->redis->sadd($prefix, $key);
            $this->redis->incr($key);
        }
    }

    public function station(Location $station)
    {
        if ($station instanceof Station) {
            $this->count('stats:stations', $station->id, array('name' => $station->name, 'x' => $station->coordinate->x, 'y' => $station->coordinate->y));
        }
    }

    public function resource($path)
    {
        $this->count('stats:resources', $path, array('path' => $path));
    }

    protected function count($prefix, $id, $data)
    {
        if ($this->enabled) {
            $key = "$prefix:$id";
            $this->redis->hmset($key, $data);
            $this->redis->sadd($prefix, $key);
            $this->redis->hincrby($key, 'calls', 1);
        }
    }

    public function getCalls()
    {
	    $keys = $this->redis->keys('stats:calls:*');

        $result = $this->redis->sort("stats:calls", array(
            'get' => array('#', '*'),
            'sort'  => 'ASC',
            'alpha' => true
        ));

	    // regroup
	    $calls = array();
	    foreach (array_chunk($result, 2) as $values) {
	        $calls[substr($values[0], 12, 10)] = $values[1];
	    }

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
