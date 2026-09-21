"""How PHP reads a query string, and why it matters here.

/v1 reads its parameters through `parse_str`, which has two habits that no
other language shares and that both change answers:

- **The last occurrence wins, and it sets the type.** `via=a&via=b` is the
  string `b`, not a list of two - so a client that repeats a parameter without
  brackets gets only its last value. `via[]=a&via[]=b` is the list. Mixing the
  two spellings means the later one decides which it is.
- **`isset` is not truthiness.** An empty string is set; a null is not. Half
  the assignments in the old mapping turn on that difference, and an empty
  string coming through as null instead is a difference in the answer.
"""

from typing import Any

from fastapi import Request


def parameter(request: Request, name: str) -> list[str] | str | None:
    """The value `parse_str` would have produced for `name`.

    A list when the last occurrence was `name[...]`, a string when it was bare
    `name`, and None when it never appeared.
    """
    current: list[str] | str | None = None
    for key, value in request.query_params.multi_items():
        if key == name:
            current = value
        elif key.startswith(f"{name}["):
            if not isinstance(current, list):
                current = []
            current.append(value)
    return current


def as_list(value: list[str] | str | None) -> list[str]:
    """`(array) $value` - a string becomes a list of one, nothing becomes none."""
    if value is None:
        return []
    if isinstance(value, str):
        return [value] if value != "" else []
    return value


def truthy(value: str | None) -> bool:
    """PHP truthiness of a query parameter.

    `if ($query || ($x && $y))` and `$request->get("station") ?: ...` treat an
    empty string and the string `"0"` as absent. A coordinate of exactly zero
    is in the Gulf of Guinea, so that has never mattered in practice - but it
    is what the old endpoint does, and the differential test compares answers,
    not intentions.
    """
    return value is not None and value != "" and value != "0"


def isset(entry: dict, key: str) -> bool:
    """`isset($json->key)` - present and not null. An empty string counts."""
    return entry.get(key) is not None


def value(entry: dict, key: str) -> Any:
    return entry.get(key)
