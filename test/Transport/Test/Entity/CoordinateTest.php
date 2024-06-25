<?php

namespace Transport\Test\Entity;

use Transport\Entity\Coordinate;

class CoordinateTest extends \PHPUnit\Framework\TestCase
{
    public static function provider()
    {
        return [
            [0, 0, 0],
            [47.476088, 47476088, 47.476088],
            [47.476088111, 47476088, 47.476088],
            [47.476088999, 47476089, 47.476089],
            [47.4, 47400000, 47.4],
        ];
    }

    /**
     * @dataProvider provider
     */
    public function testFloatToInt($float, $int)
    {
        $this->assertEquals($int, Coordinate::floatToInt($float));
    }

    /**
     * @dataProvider provider
     */
    public function testIntToFloat($source, $int, $float)
    {
        $this->assertEquals($float, Coordinate::intToFloat($int));
    }
}
