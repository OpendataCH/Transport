<?php

namespace Transport;

use Predis\Client;

class RateLimiting
{
    const KEY_PREFIX = 'rate_limiting';

    protected $redis;

    protected $enabled;

    protected $limit;

    public function __construct(Client $redis = null, $enabled = false, $limit = 150)
    {
        $this->redis = $redis;
        $this->enabled = $enabled;
        $this->limit = $limit;
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
        $minute = date('Y-m-d\TH:i');
        $prefix = self::KEY_PREFIX;

        $key = "$prefix:$ip:$minute";

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
            $tx->expire($key, 120); // expire after two minutes
        });
    }

    public function getRemaining($ip)
    {
        return $this->getLimit() - $this->getCount($ip);
    }

    public function getReset()
    {
        return ceil(time() / 60) * 60;
    }
}
