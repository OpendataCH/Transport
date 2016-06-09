<?php

namespace Transport\Normalizer;

use Symfony\Component\Serializer\Normalizer\NormalizerInterface;
use Symfony\Component\Serializer\Normalizer\SerializerAwareNormalizer;

class FieldsNormalizer extends SerializerAwareNormalizer implements NormalizerInterface
{
    private $fields = [];

    public function __construct(array $fields)
    {
        foreach ($fields as $field) {
            $this->fields = array_merge_recursive($this->fields, $this->getFieldTree($field));
        }
    }

    /**
     * returns true if the given field should be included in the result.
     *
     * @param string $field the field (e.g from)
     */
    public function isFieldSet($field)
    {
        // if no fields were set, return true, this is the default
        if (count($this->fields) == 0) {
            return true;
        }
        $fieldParts = explode('/', $field);
        $fieldFromTree = null;
        $searchTree = $this->fields;
        foreach ($fieldParts as $fieldPart) {
            if (array_key_exists($fieldPart, $searchTree)) {
                $fieldFromTree = $searchTree[$fieldPart];
            } else {
                // if a part is not set, no child fields should be included
                return false;
            }
            // if a part is set to true, all child fields should be included
            if ($fieldFromTree === true) {
                return true;
            }
            // continue the search
            $searchTree = $fieldFromTree;
        }
        // if the found field is an array,
        // there are more specific fields set,
        // so their parent should be included
        if (is_array($fieldFromTree)) {
            return true;
        }

        return false;
    }

    private function getFieldTree($field)
    {
        return array_reduce(
            array_reverse(explode('/', $field)),
            function ($result, $value) {
                return [$value => $result];
            },
            true
        );
    }

    /**
     * {@inheritdoc}
     */
    public function normalize($data, $format = null, array $context = [])
    {
        if (is_array($data)) {
            foreach ($data as $name => $value) {
                $data[$name] = $this->serializer->normalize($value, $format, $context);
            }

            return $data;
        }

        $normalized = [];
        foreach ($data as $name => $value) {
            $field = isset($context['fields_parent_field']) ? $context['fields_parent_field'].'/'.$name : $name;
            if ($this->isFieldSet($field)) {
                if (null !== $value && !is_scalar($value)) {
                    $options = [
                        'fields_parent_field' => $field,
                    ];
                    $value = $this->serializer->normalize($value, $format, array_merge($context, $options));
                }

                $normalized[$name] = $value;
            }
        }

        return $normalized;
    }

    /**
     * {@inheritdoc}
     */
    public function supportsNormalization($data, $format = null)
    {
        return is_array($data) || is_object($data);
    }
}
