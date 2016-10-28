<?php

namespace Transport;

use Predis\Client;

class RateLimiting
{
    const KEY_PREFIX = 'rate_limiting';

    protected $redis;

    protected $enabled;

    protected $limit;

    protected $second;

    public function __construct(Client $redis = null, $enabled = false, $limit = 3)
    {
        $this->redis = $redis;
        $this->enabled = $enabled;
        $this->limit = $limit;

        $this->second = time();
    }

    public function isEnabled()
    {
        return $this->enabled;
    }

    public function getLimit()
    {
        return $this->limit;
    }

    public function hasReachedLimit($ip)
    {
        $count = $this->getCount($ip);
        if ($count !== null && $count >= $this->getLimit()) {
            return true;
        }

        return false;
    }

    protected function key($ip)
    {
        $prefix = self::KEY_PREFIX;
        $second = date('Y-m-d\TH:i:s', $this->second);

        $key = "$prefix:$ip:$second";

        return $key;
    }

    public function getCount($ip)
    {
        $key = $this->key($ip);

        return $this->redis->get($key);
    }

    public function increment($ip)
    {
        $key = $this->key($ip);
        $this->redis->transaction(function ($tx) use ($key) {
            $tx->incr($key);
            $tx->expire($key, 5); // expire after five seconds
        });
    }

    public function getRemaining($ip)
    {
        return $this->getLimit() - $this->getCount($ip);
    }

    public function getReset()
    {
        return $this->second + 1;
    }
}
