"""Gate: `app.ui.kit.icons` and the `icon` macro say the same (CR-17, C4.9).

A card's icon is validated, drawn and offered from `icon_names()` and
`icon_paths()`, which read the macro's own dict. Nothing here holds a list of
names: the macro is rendered for every name the module returns, and the dict's
entries are counted a second way, so the two cannot drift apart unseen.

Proven on purpose (13 October 2026), each put back by the reverse edit:
- an entry ADDED to the macro's dict in a shape the reader does not know
  (`"zz-proof": "<path/>",` — double quotes) → the three reading tests red with
  `IconSourceError: line 1 of the icon macro's dict is not an entry`;
- an entry added in the dict's own shape (`"zz-proof": '<path d="M0 0"/>',`)
  → green, and `icon_names()` returns `zz-proof`: the list follows the macro.
"""

from __future__ import annotations

import re

import pytest

from app.ui import templates
from app.ui.kit import icons


def _source() -> str:
    return icons._SOURCE.read_text(encoding="utf-8")


def test_the_reader_returns_every_entry_of_the_macro():
    """Counted a second way: the keys between the macro's opening and its
    `viewboxes` line, by their own pattern."""
    source = _source()
    block = source[source.index("{% macro icon(") : source.index("{%- set viewboxes")]
    keys = re.findall(r'^\s+"([^"]+)":', block, re.M)
    assert len(keys) > 50, "the count itself found too little to mean anything"
    assert list(icons.icon_names()) == keys


def test_the_macro_draws_what_the_reader_returns():
    """Every name's parts are what `ui.icon(name)` renders — the reader did
    not read some other dict."""
    macro = templates.env.get_template("_macros.html").module.icon
    names = icons.icon_names()
    assert names
    for name in names:
        assert icons.icon_paths()[name] in str(macro(name)), name


def test_a_name_the_kit_does_not_know_is_not_in_the_list():
    assert "geen-icoon" not in icons.icon_names()
    assert "users" in icons.icon_names()


@pytest.mark.parametrize(
    "broken, says",
    [
        ("no macro here", "was not found"),
        ("{% macro icon(name) -%}\n{%- set paths = {\n\n} -%}", "is empty"),
        (
            '{% macro icon(name) -%}\n{%- set paths = {\n  "a": \'<path/>\',\n  "b": "<path/>",\n} -%}',
            "line 2",
        ),
        (
            "{% macro icon(name) -%}\n{%- set paths = {\n  \"a\": '<path/>',\n  \"a\": '<path/>',\n} -%}",
            "twice",
        ),
        ("{% macro icon(name) -%}\n{%- set paths = {\n  \"a\": '',\n} -%}", "no paths"),
    ],
)
def test_a_dict_that_cannot_be_read_whole_is_an_error_not_a_shorter_list(broken, says):
    with pytest.raises(icons.IconSourceError, match=says):
        icons.parse_icon_paths(broken)
