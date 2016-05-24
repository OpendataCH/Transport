<?php

namespace Transport\Entity;

abstract class Query
{
    public $lang = 'EN';

    /**
     * @return \SimpleXMLElement
     */
    protected function createRequest()
    {
        $request = new \SimpleXMLElement('<?xml version="1.0" encoding="iso-8859-1"?><ReqC />');
        $request['lang'] = $this->lang;
        $request['prod'] = \Transport\API::SBB_PROD;
        $request['ver'] = \Transport\API::SBB_VERSION;
        $request['accessId'] = \Transport\API::SBB_ACCESS_ID;

        return $request;
    }
}
