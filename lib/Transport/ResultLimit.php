<?php

namespace Transport;

/**
* ResultLimit
*/
class ResultLimit
{
    private static $fields = array();
    
    private function __construct()
    {
    }
    
    public static function setFields(array $fields)
    {
        foreach ($fields as $field) {
            self::$fields = array_merge_recursive(self::$fields, self::getFieldTree($field));
        }
    }
    
    /**
     * removes all set fields. Needed for tests.
     *
     */
    public static function unsetFields() {
        self::$fields = array();
    }

    /**
     * returns true if the given field should be included in the result.
     *
     * @param string $field the field (e.g from)
     */
    public static function isFieldSet($field)
    {
        //if no fields were set, return true, this is the default
        if (count(self::$fields) == 0) {
            return true;
        }
        $fieldParts = explode('/',$field);
        $fieldFromTree = null;
        $searchTree = self::$fields;
        foreach($fieldParts as $fieldPart) {
            if (array_key_exists($fieldPart, $searchTree)) {
                $fieldFromTree = $searchTree[$fieldPart];
            } else {
                //if a part is not set, no child fields should be included
                return false;
            }
            //if a part is set to true, all child fields should be included
            if ($fieldFromTree === true) {
                return true;
            }
            //continue the search
            $searchTree = $fieldFromTree;
        }
        //if the found field is an array,
        //there are more specific fields set,
        //so their parent should be included
        if (is_array($fieldFromTree)) {
            return true;
        }
        return false;
    }

    private static function getFieldTree($field)
    {
        return array_reduce(
            array_reverse(explode('/', $field)),
            function ($result, $value) { return array($value => $result); },
            true
        );
    }
}