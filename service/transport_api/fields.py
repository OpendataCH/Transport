"""`fields[]` - the sparse-fieldset filter of /v1.

Seventy-five quiet lines in the PHP, publicly documented, and in real use: in a
ten-minute slice of the live access log, 788 of 41,176 requests carry it. It is
the single most likely thing to get subtly wrong, so its rules are written out
here and each one is a test.

A field is a `/`-separated path of **object keys**; lists are transparent, so
`stationboard/stop/departure` reaches into every entry of the board. The paths
are merged into a tree, and then:

- a part that is not in the tree drops the value and everything below it;
- a part whose subtree is `True` keeps everything below it;
- a part with a subtree is kept because something below it was asked for.

Two consequences that surprise everyone:

- **Narrow beats broad.** `fields[]=stations` and `fields[]=stations/name`
  together give only the name. The PHP merges the two into one subtree and the
  `True` stops being reachable.
- **An object that loses every key becomes `[]`, not `{}`.** The PHP builds the
  filtered object in an array, and an empty array encodes as a JSON list. So a
  request for a field nobody has answers `[]` - the whole document.
"""

from dataclasses import dataclass
from typing import Any

from fastapi import Request

from .query import parameter

# True means "everything below here"; a dict means "only what is named".
Tree = dict[str, Any]


def tree_of(paths: list[str]) -> Tree:
    """Merge `a/b`, `a/c` into `{a: {b: True, c: True}}`."""
    tree: Tree = {}
    for path in paths:
        _graft(tree, [part for part in path.split("/") if part != ""])
    return tree


def _graft(tree: Tree, parts: list[str]) -> None:
    if not parts:
        return

    head, rest = parts[0], parts[1:]
    if not rest:
        # A leaf only takes hold where nothing more specific stands. The PHP
        # keeps both and can no longer reach the `true`; the effect is that the
        # narrower path wins, and this is where that happens.
        tree.setdefault(head, True)
        return

    if not isinstance(tree.get(head), dict):
        tree[head] = {}
    _graft(tree[head], rest)


def is_set(tree: Tree, path: str) -> bool:
    """Is this path asked for? With no fields at all, everything is."""
    if not tree:
        return True

    node: Any = None
    search: Any = tree
    for part in path.split("/"):
        if isinstance(search, dict) and part in search:
            node = search[part]
        else:
            # A part that is not named drops the whole subtree.
            return False
        if node is True:
            return True
        search = node

    # Something more specific below was asked for, so the parent is needed.
    return isinstance(node, dict)


def apply(value: Any, tree: Tree, path: str = "") -> Any:
    """Filter an answer. Lists are walked without adding to the path."""
    if not tree:
        return value

    if isinstance(value, list):
        return [apply(item, tree, path) for item in value]

    if isinstance(value, dict):
        kept = {}
        for key, item in value.items():
            here = f"{path}/{key}" if path else key
            if is_set(tree, here):
                kept[key] = apply(item, tree, here) if _descends(item) else item
        # An object stripped of every key comes back as an empty *list*,
        # because the PHP builds it in an array. See the module docstring.
        return kept or []

    return value


def _descends(value: Any) -> bool:
    """The PHP recurses into anything that is neither null nor scalar."""
    return isinstance(value, list | dict)


class NotAList(Exception):
    """`fields=x` without the brackets.

    The PHP hands the string to a constructor that wants an array, and the
    TypeError escapes the error handler: the caller gets a 500 with an empty
    body and no explanation. Reproduced, because a client that sends this today
    already lives with it.
    """


@dataclass(frozen=True)
class Fields:
    """The `fields[]` of one request, ready to filter an answer with."""

    tree: Tree

    def apply(self, value: Any) -> Any:
        return apply(value, self.tree)

    @classmethod
    def of(cls, request: Request) -> "Fields":
        """Read the parameter the way PHP's parse_str does.

        `fields[]` appends to a list, a bare `fields` replaces the whole thing
        with a string - and the **last** occurrence in the query string decides
        which of the two the parameter is.
        """
        current = parameter(request, "fields")

        if isinstance(current, str):
            raise NotAList(current)

        return cls(tree_of(current or []))
