"""The kit's icon vocabulary, readable from Python (CR-17, C4.9).

The names and their paths live in ONE place: the `paths` dict of the `icon`
macro in `templates/_macros.html`. A card on a page picks an icon by name, and
three places need the list — the schema (is this a name the kit knows?), the
renderer (the paths, to draw the icon on the public page) and the card dialog
(the choices). None of them keeps a copy: they ask here, and this module reads
the macro's own text. The macro itself is untouched.

The read fails loudly. A line of the dict the parser cannot read, an empty
dict or a macro that moved raises `IconSourceError` — never a shorter list,
because a card that held a name the list lost would be refused at the next
save. `tests/test_icon_names_gate.py` holds the two together.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

_SOURCE = Path(__file__).parent.parent / "templates" / "_macros.html"

#: The dict's text: from the macro's opening to the `} -%}` that closes the dict
#: (it stands at the end of the last entry's own line).
_DICT = re.compile(r"\{% macro icon\(.*?\{%- set paths = \{\n(.*?)\} -%\}", re.S)
#: One entry: `  "name": '<svg parts>',`
_ENTRY = re.compile(r"""^\s*"([a-z0-9-]+)":\s*'([^']*)',?\s*$""")


class IconSourceError(RuntimeError):
    """The `icon` macro's dict could not be read whole."""


def parse_icon_paths(source: str) -> dict[str, str]:
    """The `paths` dict of the `icon` macro in `source`, as name → SVG parts.

    Every line of the dict must be an entry: one that is not is an error, not a
    name left out.
    """
    found = _DICT.search(source)
    if not found:
        raise IconSourceError("the icon macro's paths dict was not found in _macros.html")
    paths: dict[str, str] = {}
    for number, line in enumerate(found.group(1).splitlines(), start=1):
        if not line.strip():
            continue
        entry = _ENTRY.match(line)
        if not entry:
            raise IconSourceError(
                f"line {number} of the icon macro's dict is not an entry: {line[:60]!r}"
            )
        name, parts = entry.group(1), entry.group(2)
        if name in paths:
            raise IconSourceError(f"the icon macro's dict names {name!r} twice")
        if not parts:
            raise IconSourceError(f"the icon {name!r} has no paths")
        paths[name] = parts
    if not paths:
        raise IconSourceError("the icon macro's paths dict is empty")
    return paths


@lru_cache(maxsize=1)
def icon_paths() -> dict[str, str]:
    """Every icon of the kit: name → the SVG parts the macro draws."""
    return parse_icon_paths(_SOURCE.read_text(encoding="utf-8"))


def icon_names() -> tuple[str, ...]:
    """The names the kit's `icon` macro knows, in the macro's order."""
    return tuple(icon_paths())
