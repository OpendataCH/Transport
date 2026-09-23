<?php

namespace Transport;

use Predis\Client;
use Transport\Entity\Location\Location;
use Transport\Entity\Location\Station;

class Statistics
{
    /**
     * How long the hourly buckets are kept, in seconds (35 days).
     */
    const HOURLY_TTL = 3024000;

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
            $this->hourly(['calls' => 1]);
        }
    }

    /**
     * Counts a request rejected with HTTP 429, by this API or by timetable.search.ch.
     */
    public function rateLimited()
    {
        if ($this->enabled) {
            $this->hourly(['ratelimited' => 1]);
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
            $this->hourly(['errors' => 1, "exception:$exceptionClass" => 1]);
        }

        $this->count('stats:exceptions', $exceptionClass, ['exception' => $exceptionClass]);
    }

    /**
     * Increments fields of the bucket for the current hour, which expires after HOURLY_TTL.
     *
     * @param array $increments field => amount
     */
    protected function hourly(array $increments)
    {
        $key = 'stats:hourly:'.date('Y-m-d\TH');
        $this->redis->pipeline(function ($pipe) use ($key, $increments) {
            foreach ($increments as $field => $amount) {
                $pipe->hincrby($key, $field, $amount);
            }
            $pipe->expire($key, self::HOURLY_TTL);
        });
    }

    /**
     * The hourly buckets of the last $hours hours, oldest first, the current hour included.
     *
     * Each entry carries the start of the hour, the calls, errors and rate-limited requests,
     * the errors per exception class, and whether the bucket exists at all.
     *
     * @param int $hours
     *
     * @return array
     */
    public function getHourly($hours)
    {
        $now = time();
        $starts = [];
        for ($i = $hours - 1; $i >= 0; $i--) {
            $starts[] = $now - $i * 3600;
        }

        $buckets = $this->redis->pipeline(function ($pipe) use ($starts) {
            foreach ($starts as $start) {
                $pipe->hgetall('stats:hourly:'.date('Y-m-d\TH', $start));
            }
        });

        $result = [];
        foreach ($starts as $index => $start) {
            $bucket = $buckets[$index] ?: [];
            $exceptions = [];
            foreach ($bucket as $field => $value) {
                if (strpos($field, 'exception:') === 0) {
                    $exceptions[substr($field, 10)] = (int) $value;
                }
            }
            $result[] = [
                'hour'        => date('Y-m-d\TH:00', $start),
                'recorded'    => !empty($bucket),
                'calls'       => isset($bucket['calls']) ? (int) $bucket['calls'] : 0,
                'errors'      => isset($bucket['errors']) ? (int) $bucket['errors'] : 0,
                'ratelimited' => isset($bucket['ratelimited']) ? (int) $bucket['ratelimited'] : 0,
                'exceptions'  => $exceptions,
            ];
        }

        return $result;
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

    /**
     * Calls and errors of the last $days calendar days, oldest first, today included.
     *
     * @param int $days
     *
     * @return array date => ['calls' => int, 'errors' => int]
     */
    public function getDays($days)
    {
        $dates = [];
        for ($i = $days - 1; $i >= 0; $i--) {
            $dates[] = date('Y-m-d', strtotime("-$i days"));
        }

        $calls = $this->redis->mget(array_map(function ($date) {
            return "stats:calls:$date";
        }, $dates));
        $errors = $this->redis->mget(array_map(function ($date) {
            return "stats:errors:$date";
        }, $dates));

        $result = [];
        foreach ($dates as $index => $date) {
            $result[$date] = ['calls' => (int) $calls[$index], 'errors' => (int) $errors[$index]];
        }

        return $result;
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
     * All recorded exception classes, most frequent first.
     */
    public function getExceptions()
    {
        return $this->top('stats:exceptions', ['exception', 'calls'], 100);
    }

    /**
     * @param string   $key
     * @param string[] $fields
     * @param int      $limit
     */
    protected function top($key, $fields, $limit = 5)
    {
        $result = $this->redis->sort($key, [
            'by'    => '*->calls',
            'limit' => [0, $limit],
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
