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
        $this->count('stats:stations', $station->id, $station->name);
    }

    public function resource($path)
    {
        $this->count('stats:resources', $path, $path);
    }

    protected function count($prefix, $id, $value)
    {
        if ($this->redis) {
            $key = "$prefix:$id";
            $this->redis->set($key, $value);
            $this->redis->sadd($prefix, $key);
            $this->redis->incr("$key:calls");
        }
    }
    
    public function getTopResources()
    {
        return $this->top('stats:resources');
    }

    public function getTopStations()
    {
        return $this->top('stats:stations');
    }

    protected function top($key)
    {
        $result = $this->redis->sort($key, array(
            'by' => '*:calls',
            'limit' => array(0, 5),
            'get' => array('*', '*:calls'),
            'sort'  => 'DESC',
        ));

        // regroup
        $data = array();
        for ($i = 0; $i < count($result); $i += 2) {
            $data[$result[$i]] = $result[$i + 1];
        }

        return $data;
    }
}
