<?php

namespace Transport\Test\Entity\Location;

use Transport\Entity\Location\LocationQuery;

class LocationQueryTest extends \PHPUnit_Framework_TestCase
{
    public static function provider()
    {
        return array(
            array(null, 'ALLTYPE'),
            array('all', 'ALLTYPE'),
            array('station', 'ST'),
            array('address', 'ADR'),
            array('poi', 'POI'),
        );
    }

    /**
     * @dataProvider provider
     */
    public function testToXml($type, $expected)
    {
        $query = new LocationQuery('Ber', $type);

        $this->assertEquals('<?xml version="1.0" encoding="iso-8859-1"?>
<ReqC lang="EN" prod="iPhone3.1" ver="2.3" accessId="vWjygiRIy0uclbLz4qDO7S3G4dcIIViwoLFCZlopGhe88vlsfedGIqctZP9lvqb"><LocValReq id="0" sMode="1"><ReqLoc match="Ber" type="' . $expected . '"/></LocValReq></ReqC>
', $query->toXml());
    }

    /**
     * @dataProvider provider
     */
    public function testArrayToXml($type, $expected)
    {
        $query = new LocationQuery(array('from' => 'ZÃ¼rich', 'to' => 'Bern'), $type);

        $this->assertEquals('<?xml version="1.0" encoding="iso-8859-1"?>
<ReqC lang="EN" prod="iPhone3.1" ver="2.3" accessId="vWjygiRIy0uclbLz4qDO7S3G4dcIIViwoLFCZlopGhe88vlsfedGIqctZP9lvqb"><LocValReq id="from" sMode="1"><ReqLoc match="Zürich" type="' . $expected . '"/></LocValReq><LocValReq id="to" sMode="1"><ReqLoc match="Bern" type="' . $expected . '"/></LocValReq></ReqC>
', $query->toXml());
    }
}

