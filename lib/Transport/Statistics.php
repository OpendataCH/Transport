<?php

namespace Transport;

use Predis\Client;
use Transport\Entity\Location\Location;
use Transport\Entity\Location\Station;

class Statistics
{
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
            $prefix = 'stats:calls';
            $key = "$prefix:$date";
            $this->redis->sadd($prefix, $key);
            $this->redis->incr($key);
        }
    }

    public function station(Location $station)
    {
        if ($station instanceof Station) {
            $this->count('stats:stations', $station->id, ['name' => $station->name, 'x' => $station->coordinate->x, 'y' => $station->coordinate->y]);
        }
    }

    /**
     * @param string $path
     */
    public function resource($path)
    {
        $this->count('stats:resources', $path, ['path' => $path]);
    }

    public function error($e)
    {
        $exceptionClass = get_class($e);

        if ($this->enabled) {
            $date = date('Y-m-d');
            $prefix = 'stats:errors';
            $key = "$prefix:$date";
            $this->redis->sadd($prefix, $key);
            $this->redis->incr($key);
        }

        $this->count('stats:exceptions', $exceptionClass, ['exception' => $exceptionClass]);
    }

    /**
     * @param string $prefix
     * @param string $id
     * @param array  $data
     */
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
        $result = $this->redis->sort('stats:calls', [
            'get'   => ['#', '*'],
            'sort'  => 'ASC',
            'alpha' => true,
        ]);

        // regroup
        $calls = [];
        foreach (array_chunk($result, 2) as $values) {
            $calls[substr($values[0], 12, 10)] = $values[1];
        }

        return $calls;
    }

    public function getErrors()
    {
        $result = $this->redis->sort('stats:errors', [
            'get'   => ['#', '*'],
            'sort'  => 'ASC',
            'alpha' => true,
        ]);

        // regroup
        $errors = [];
        foreach (array_chunk($result, 2) as $values) {
            $errors[substr($values[0], 13, 10)] = $values[1];
        }

        return $errors;
    }

    public function getTopResources()
    {
        return $this->top('stats:resources', ['path', 'calls']);
    }

    public function getTopStations()
    {
        return $this->top('stats:stations', ['name', 'x', 'y', 'calls']);
    }

    public function getTopExceptions()
    {
        return $this->top('stats:exceptions', ['exception', 'calls']);
    }

    /**
     * @param string   $key
     * @param string[] $fields
     */
    protected function top($key, $fields)
    {
        $result = $this->redis->sort($key, [
            'by'    => '*->calls',
            'limit' => [0, 5],
            'get'   => array_map(function ($value) {
                return "*->$value";
            }, $fields),
            'sort'  => 'DESC',
        ]);

        // regroup
        $data = [];
        foreach (array_chunk($result, count($fields)) as $values) {
            $data[] = array_combine($fields, $values);
        }

        return $data;
    }
}
