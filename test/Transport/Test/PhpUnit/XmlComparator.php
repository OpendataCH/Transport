<?php

namespace Transport\Test\PhpUnit;

use SebastianBergmann\Comparator\ScalarComparator;

class XmlComparator extends ScalarComparator
{
    public function accepts($expected, $actual)
    {
        return $expected instanceof \SimpleXMLElement && is_string($actual);
    }

    public function assertEquals($expected, $actual, $delta = 0.0, $canonicalize = false, $ignoreCase = false)
    {
        $expectedAsString = $expected->asXML();
        $actualAsString = $this->xmlToText($actual);

        parent::assertEquals($expectedAsString, $actualAsString, $delta, $canonicalize, $ignoreCase);
    }

    private function xmlToText($xml)
    {
        $dom = new \DOMDocument();
        $dom->loadXML($xml);

        $dom->formatOutput = true;
        $dom->preserveWhiteSpace = false;
        $dom->normalizeDocument();

        $text = $dom->saveXML();

        return $text;
    }
}
