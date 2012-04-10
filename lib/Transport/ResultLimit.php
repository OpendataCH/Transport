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
            self::$fields = array_merge(self::$fields, self::getFieldTree($field));
        }
    }

    /**
     * returns true if the given field should be included in the result.
     *
     * @param string $field the field (e.g from)
     * @param array $searchBase an array with given fields in a tree, only needed for recursion
     */
    public static function isFieldSet($field, $searchBase = null)
    {
        //if no fields were set, return true, this is the default
        if (self::$fields === null) {
            return true;
        }
        //if not yet in a recursive loop, use the top of the tree as the search base
        if ($searchBase === null) {
            $searchBase = self::$fields;
        }
        //if this is not a nested field, we may find it at the top
        if (array_key_exists($field, $searchBase)) {
            return true;
        //if it's not found, let's dig deeper
        } else {
            foreach ($searchBase as $newSearchBase) {
                if (is_array($newSearchBase)) {
                    $result = self::isFieldSet($field, $newSearchBase);    
                }
                //if the field is found, return this information to stop crawling at this point
                if ($result) {
                    return $result;    
                }
            }
            //the field doesn't seem to be set
            return false;   
        }    
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