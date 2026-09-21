"""Comparing two JSON answers, strictly.

Shared by the two tools beside it. The rules are the ones the plan names:
order-aware for lists, order-insensitive for object keys, `null` kept strictly
apart from a missing key - and types compared, because `9` and `9.0` are the
same number and a different answer.
"""

import re


def differences(left, right, path: str = ""):
    """Every place the two answers are not the same thing."""
    if isinstance(left, dict) and isinstance(right, dict):
        for key in sorted(set(left) | set(right)):
            where = f"{path}.{key}"
            if key not in left:
                yield f"{where}: only in /v2 ({right[key]!r})"
            elif key not in right:
                yield f"{where}: only in /v1 ({left[key]!r})"
            else:
                yield from differences(left[key], right[key], where)
    elif isinstance(left, list) and isinstance(right, list):
        if len(left) != len(right):
            yield f"{path}: {len(left)} entries in /v1, {len(right)} in /v2"
        for index, (one, other) in enumerate(zip(left, right, strict=False)):
            yield from differences(one, other, f"{path}[{index}]")
    elif type(left) is not type(right) or left != right:
        yield f"{path}: /v1 {left!r} != /v2 {right!r}"


def field(difference: str) -> str:
    """The field a difference is about, with list positions collapsed.

    `connections[3].sections[0].departure.delay` becomes
    `connections[].sections[].departure.delay`, so that a tally counts fields
    rather than occurrences.
    """
    where = difference.split(":", 1)[0].lstrip(".")
    return re.sub(r"\[\d+\]", "[]", where) or "(the whole answer)"
