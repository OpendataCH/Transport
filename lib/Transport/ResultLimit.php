<?php

namespace Transport;

/**
 * ResultLimit
 */
class ResultLimit
{
    private $fields = null;
    
    private static $instance = null;
    
    // basic singleton pattern
    private static function getInstance() {
        if (self::$instance === null) {
            self::$instance = new ResultLimit;
        }
        return self::$instance;
    }
    
    public static function setFields($fields) {
        if (is_array($fields)) {
            self::getInstance()->fields = array();
            foreach ($fields as $field) {
                self::getInstance()->fields = array_merge(self::getInstance()->fields,self::getInstance()->getFieldTree($field));
            }
        }
    }
    
    public static function includeField($field, $searchBase = null) {
        //if no fields were set, return true, this is the default
        if (self::getInstance()->fields === null) {
            return true;
        }
        //if not yet in a recursive loop, use the top of the tree as the search base
        if ($searchBase === null) {
            $searchBase = self::getInstance()->fields;
        }
        //if this is not a nested field, we may find it at the top
        if (array_key_exists($field,$searchBase)) {
            return true;
        //if it's not found, let's dig deeper
        } else {
            foreach ($searchBase as $newSearchBase) {
                if (is_array($newSearchBase)) {
                    $result = self::includeField($field,$newSearchBase);    
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
    
    private function getFieldTree($field) {
        $remainingField = '';
        //is this field a tree?
        $delimiterPos = strpos($field,'/');
        //no
        if ($delimiterPos === false) {
            //then return the array
            return array($field => true);
        //yes
        } else {
            $result = array();
            //split up the top most element...
            $fieldTreeElement = substr($field,0,$delimiterPos);
            //...and the remaining part
            $remainingField = substr($field,strpos($field,'/')+1);
            //if there is more in this tree, recursively add it to the result
            if (strlen($remainingField)>0) {
                $result[$fieldTreeElement] = self::getInstance()->getFieldTree($remainingField);
            } else {
                $result[$fieldTreeElement] = true;
            }
            return $result;
        }
    }
}