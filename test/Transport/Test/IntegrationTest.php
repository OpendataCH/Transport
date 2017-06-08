<?php

namespace Transport\Test;

use Silex\WebTestCase;

abstract class IntegrationTest extends WebTestCase
{
    protected $browser;

    public function createApplication()
    {
        $app = new \Transport\Application();

        $app['debug'] = false;

        // uncomment the following lines for debugging
        //$app['debug'] = true;
        //unset($app['exception_handler']);

        $this->browser = $this->getMock('Buzz\\Browser', ['send']);

        $app['api'] = new \Transport\API($this->browser);

        return $app;
    }

    public function getBrowser()
    {
        return $this->browser;
    }

    public function json($response)
    {
        $content = $response->getContent();

        $json = json_decode($content);
        $json = json_encode($json, JSON_PRETTY_PRINT);

        $json .= "\n";

        return $json;
    }

    public function getFixture($filename)
    {
        return file_get_contents(__DIR__.'/../../fixtures/'.$filename);
    }

    public function getXmlFixture($filename)
    {
        return simplexml_load_string($this->getFixture($filename));
    }
}
