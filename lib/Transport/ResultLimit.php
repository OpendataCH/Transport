<?php

namespace Transport;

/**
 * ResultLimit
 */
class ResultLimit
{
    private static $fields = null;
    
    private function __construct()
    {
    }
    
    public static function setFields(array $fields)
    {
        self::$fields = array();
        foreach ($fields as $field) {
            self::$fields = array_merge_recursive(self::$fields, self::getFieldTree($field));
        }
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
        foreach($fieldParts as $fieldPart) {
            $fieldFromTree = self::getFieldFromTree($fieldPart,$fieldFromTree);
            //if a part is set to true, all child fields should be included
            if ($fieldFromTree === true) {
                return true;    
            }
            //if a part is not set, no child fields should be included
            if ($fieldFromTree === false) {
                return false;
            }
        }
        //if the searched field is an array,
        //there are more specific fields set,
        //so their parent should be included
        if (is_array($fieldFromTree)) {
            return true;    
        }
        return false;
    }
    
    private static function getFieldFromTree($field, $searchTree)
    {
        if ($searchTree === null) {
            $searchTree = self::$fields;
        }
        if (array_key_exists($field, $searchTree)) {
            return $searchTree[$field];
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