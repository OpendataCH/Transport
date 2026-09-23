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

    /**
     * How long the daily lists of stations and pairs are kept (35 days), and how
     * many of each a finished day keeps.
     */
    const TOP_TTL = 3024000;
    const TOP_KEEP = 500;

    /**
     * Today's client hashes need only outlive the day (3 days); the summary of a
     * finished day is kept for 400 days.
     */
    const CLIENTS_TTL = 259200;
    const SUMMARY_TTL = 34560000;

    /**
     * Kinds of client, first match wins. The same list, in the same order, is in
     * service/transport_api/statistics.py - change both, or the two halves of one
     * history disagree about what a client is.
     */
    const CLIENT_KINDS = [
        'homeassistant'   => '/homeassistant/i',
        'microcontroller' => '/esp32|esp8266|arduino|micropython/i',
        'app'             => '/dalvik|cfnetwork|okhttp/i',
        'browser'         => '/mozilla/i',
        'script'          => '/python|aiohttp|node|axios|got \(|guzzle|curl|wget|java|jetty|go-http-client|ruby|php|perl|postman|insomnia|reqwest|dart|apache-httpclient|powershell|libwww|deno|bun\//i',
    ];

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

    /**
     * Counts who asked: the kind of client per hour, and a hash of the address per day.
     *
     * The hash is keyed with a secret and the date, so it means nothing outside
     * its day, and once the day is over only a summary of it is kept.
     *
     * @param string|null $ip
     * @param string|null $userAgent
     */
    public function client($ip, $userAgent)
    {
        if (!$this->enabled) {
            return;
        }

        $this->hourly(['client:'.self::clientKind($userAgent) => 1]);

        if ($ip) {
            $date = date('Y-m-d');
            $key = "stats:clients:$date";
            $this->redis->zincrby($key, 1, substr(hash_hmac('sha256', "$date|$ip", $this->secret()), 0, 16));
            $this->redis->expire($key, self::CLIENTS_TTL);
        }

        $this->rollOver();
    }

    /**
     * Counts the station of a board, or the pair of a connection search, as asked for.
     *
     * @param string $path
     * @param array  $params
     */
    public function places($path, array $params)
    {
        if (!$this->enabled) {
            return;
        }

        $date = date('Y-m-d');
        if (substr($path, -strlen('/stationboard')) === '/stationboard') {
            $station = self::cleanName(!empty($params['station']) ? $params['station'] : (isset($params['id']) ? $params['id'] : null));
            if ($station !== null) {
                $this->redis->zincrby("stats:top:stations:$date", 1, $station);
                $this->redis->expire("stats:top:stations:$date", self::TOP_TTL);
            }
        } elseif (substr($path, -strlen('/connections')) === '/connections') {
            $from = self::cleanName(isset($params['from']) ? $params['from'] : null);
            $to = self::cleanName(isset($params['to']) ? $params['to'] : null);
            if ($from !== null && $to !== null) {
                $this->redis->zincrby("stats:top:routes:$date", 1, "$from → $to");
                $this->redis->expire("stats:top:routes:$date", self::TOP_TTL);
            }
        }
    }

    /**
     * The kind of client a User-Agent names: a key of CLIENT_KINDS, or none/other.
     *
     * @param string|null $userAgent
     *
     * @return string
     */
    public static function clientKind($userAgent)
    {
        if (!$userAgent || $userAgent === '-') {
            return 'none';
        }
        foreach (self::CLIENT_KINDS as $kind => $pattern) {
            if (preg_match($pattern, $userAgent)) {
                return $kind;
            }
        }

        return 'other';
    }

    /**
     * A station or place as asked for, with its whitespace tidied, or null.
     *
     * @param mixed $value
     *
     * @return string|null
     */
    public static function cleanName($value)
    {
        if (!is_string($value)) {
            return null;
        }
        $value = mb_substr(trim(preg_replace('/\s+/u', ' ', $value)), 0, 80);

        return $value === '' ? null : $value;
    }

    /**
     * How many clients there were, and how few of them made half and 90 % of the calls.
     *
     * @param int[] $counts
     *
     * @return array
     */
    public static function summarise(array $counts)
    {
        rsort($counts);
        $total = array_sum($counts);
        $summary = ['clients' => count($counts), 'requests' => $total, 'half' => 0, 'ninety' => 0, 'top10' => array_sum(array_slice($counts, 0, 10))];
        $running = 0;
        foreach ($counts as $index => $count) {
            $running += $count;
            if (!$summary['half'] && $running * 2 >= $total) {
                $summary['half'] = $index + 1;
            }
            if (!$summary['ninety'] && $running * 10 >= $total * 9) {
                $summary['ninety'] = $index + 1;
                break;
            }
        }

        return $summary;
    }

    /**
     * The key for the client hashes, made once and shared with the Python service.
     *
     * @return string
     */
    protected function secret()
    {
        $this->redis->set('stats:secret', bin2hex(random_bytes(32)), 'NX');

        return $this->redis->get('stats:secret');
    }

    /**
     * Once per day, whoever gets there first boils yesterday down.
     */
    protected function rollOver()
    {
        $yesterday = date('Y-m-d', strtotime('-1 day'));
        if (!$this->redis->set("stats:rollover:$yesterday", 1, 'EX', self::CLIENTS_TTL, 'NX')) {
            return;
        }

        foreach (['stations', 'routes'] as $kind) {
            $this->redis->zremrangebyrank("stats:top:$kind:$yesterday", 0, -self::TOP_KEEP - 1);
        }

        $clients = "stats:clients:$yesterday";
        $counts = array_map('intval', array_values($this->redis->zrange($clients, 0, -1, ['withscores' => true])));
        if ($counts) {
            $summary = "stats:clients:summary:$yesterday";
            $this->redis->hmset($summary, self::summarise($counts));
            $this->redis->expire($summary, self::SUMMARY_TTL);
        }
        $this->redis->del([$clients]);
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
            $clients = [];
            foreach ($bucket as $field => $value) {
                if (strpos($field, 'exception:') === 0) {
                    $exceptions[substr($field, 10)] = (int) $value;
                } elseif (strpos($field, 'client:') === 0) {
                    $clients[substr($field, 7)] = (int) $value;
                }
            }
            $result[] = [
                'hour'        => date('Y-m-d\TH:00', $start),
                'recorded'    => !empty($bucket),
                'calls'       => isset($bucket['calls']) ? (int) $bucket['calls'] : 0,
                'errors'      => isset($bucket['errors']) ? (int) $bucket['errors'] : 0,
                'ratelimited' => isset($bucket['ratelimited']) ? (int) $bucket['ratelimited'] : 0,
                'exceptions'  => $exceptions,
                'clients'     => $clients,
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

    /**
     * The most asked-for stations or pairs over some days.
     *
     * @param string   $kind  "stations" or "routes"
     * @param string[] $dates
     * @param int      $count
     *
     * @return array name => requests, most first
     */
    public function getTop($kind, array $dates, $count = 10)
    {
        $keys = array_map(function ($date) use ($kind) {
            return "stats:top:$kind:$date";
        }, $dates);
        if (count($keys) == 1) {
            return $this->redis->zrevrange($keys[0], 0, $count - 1, ['withscores' => true]);
        }

        // Redis 5 on the old host has no ZUNION, so the union goes through a
        // short-lived key.
        $union = 'stats:tmp:'.bin2hex(random_bytes(8));
        $this->redis->zunionstore($union, $keys);
        $this->redis->expire($union, 60);
        $top = $this->redis->zrevrange($union, 0, $count - 1, ['withscores' => true]);
        $this->redis->del([$union]);

        return $top;
    }

    /**
     * Distinct clients per day: the summary of a finished day, today counted live.
     *
     * @param string[] $dates
     *
     * @return array date => ['clients', 'requests', 'half', 'ninety', 'top10'], missing days left out
     */
    public function getClientDays(array $dates)
    {
        $result = [];
        $today = date('Y-m-d');
        foreach ($dates as $date) {
            if ($date == $today) {
                $counts = array_map('intval', array_values($this->redis->zrange("stats:clients:$date", 0, -1, ['withscores' => true])));
                if ($counts) {
                    $result[$date] = self::summarise($counts);
                }
            } else {
                $summary = $this->redis->hgetall("stats:clients:summary:$date");
                if ($summary) {
                    $result[$date] = array_map('intval', $summary);
                }
            }
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
