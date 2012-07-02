<?php

namespace Transport;

use Predis\Client;

class Statistics {

    protected $redis;

    public function __construct($redis)
    {
        $this->redis = $redis;
    }
    
    public function getTopResources()
    {
        return $this->top('stats:resources');
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
