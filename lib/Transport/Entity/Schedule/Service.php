<?php

namespace Transport\Entity\Schedule;

/**
 * Operation information for a connection.
 *
 * @SWG\Definition()
 */
class Service
{
    /**
     * Information about how regular a connection operates (e.g. daily).
     * @var string
     * @SWG\Property()
     */
    public $regular;

    /**
     * Additional information about irregular operation dates (e.g. not 23., 24. Jun 2012).
     * @var string
     * @SWG\Property()
     */
    public $irregular;
}
