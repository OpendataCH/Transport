<?php

namespace Transport\Entity\Schedule;

/**
 * Request for a station board Journey
 *
    <STBJourney>
        <JHandle tNr="3121" puic="095" cycle="00" />
        <MainStop>
            <BasicStop>
                <Station name="Zürich HB" x="8540192" y="47378177" type="WGS84" externalId="8503000#95" externalStationNr="8503000" />
                <Arr>
                    <Time>16:37</Time>
                    <Platform>
                        <Text>23/24</Text>
                    </Platform>
                </Arr>
                <StopPrognosis>
                    <Arr>
                        <Platform>
                            <Text>24</Text>
                        </Platform>
                    </Arr>
                    <Capacity1st>-1</Capacity1st>
                    <Capacity2nd>-1</Capacity2nd>
                </StopPrognosis>
            </BasicStop>
        </MainStop>
        <JourneyAttributeList>
            <JourneyAttribute from="7" to="8">
                <Attribute type="NAME">
                    <AttributeVariant type="NORMAL">
                        <Text>S1519565</Text>
                    </AttributeVariant>
                </Attribute>
            </JourneyAttribute>
            [... more <JourneyAttribute>'s]
        </JourneyAttributeList>
    </STBJourney>
 */

class StationBoardJourney
{
    /**
     * @var Transport\Entity\Schedule\Stop
     */
    public $stop;

    /**
     * @var string
     */
    public $name;

    /**
     * @var string
     */
    public $category;

    /**
     * @var string
     */
    public $operator;

    /**
     * @var string
     */
    public $to;

    static public function createFromXml(\SimpleXMLElement $xml, StationBoardJourney $obj = null)
    {
        if (!$obj) {
            $obj = new StationBoardJourney();
        }

        $obj->stop = Stop::createFromXml($xml->MainStop->BasicStop);

        // TODO: get attributes
        foreach ($xml->JourneyAttributeList->JourneyAttribute AS $journeyAttribute) {
        
            switch ($journeyAttribute->Attribute['type']) {
                case 'NAME':
                    $obj->name = (string) $journeyAttribute->Attribute->AttributeVariant->Text;
                    break;
                case 'CATEGORY':
                    $obj->category = (string) $journeyAttribute->Attribute->AttributeVariant->Text;
                    break;
                case 'OPERATOR':
                    $obj->operator = (string) $journeyAttribute->Attribute->AttributeVariant->Text;
                    break;
                case 'DIRECTION':
                    $obj->to = utf8_decode((string) $journeyAttribute->Attribute->AttributeVariant->Text);
                    break;
            }
        }

        return $obj;
    }
}
