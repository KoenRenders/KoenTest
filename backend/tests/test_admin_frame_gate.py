"""The admin frame keeps one navigation source (CR-11 block 1, #1482).

The sidebar is wide, a rail and, on a phone, a drawer — three appearances of
one element. A second loop over the menu items (for the rail, for the drawer)
is how the old phone menu drifted from the sidebar (#714, #737), so:

- `admin_base.html` loops over the menu's items exactly once, and has no
  `admin-nav-mobiel`;
- every item of the menu layout has an icon, because the rail shows an item
  by its icon alone;
- every one of those icons exists in `ui.icon`'s set — an unknown name renders
  an empty square, which is an empty rail button.

Proven by violation: a second `{% for item in groep["items"] %}` added to
admin_base.html turns the first test red; an icon name changed to one the kit
lacks ("users-x") turns the last red, naming it.
"""

from __future__ import annotations

import re
from pathlib import Path

from app.ui import _ADMIN_NAV, _ADMIN_NAV_ICONS, templates

BASE = Path(__file__).resolve().parents[1] / "app" / "ui" / "templates" / "admin_base.html"
LOOP = re.compile(
    r"\{%-?\s*for\s+\w+\s+in\s+\w+\[\"items\"\]|\{%-?\s*for\s+\w+\s+in\s+\w+\.items\b"
)


def _source() -> str:
    text = BASE.read_text()
    assert "admin-nav-zijbalk" in text, "the gate reads the admin shell"
    return re.sub(r"\{#.*?#\}", "", text, flags=re.S)


def test_the_admin_shell_has_one_navigation_source():
    source = _source()
    loops = LOOP.findall(source)
    assert len(loops) == 1, f"{len(loops)} loops over the menu's items in admin_base.html: {loops}"
    assert "admin-nav-mobiel" not in source, "a second navigation for the phone is back"


def test_every_menu_item_has_an_icon():
    hrefs = [href for href, _label in _ADMIN_NAV]
    assert len(hrefs) >= 13, "the gate reads the menu"
    missing = [href for href in hrefs if href not in _ADMIN_NAV_ICONS]
    assert not missing, f"menu items without an icon in the rail: {missing}"


def test_every_menu_icon_exists_in_the_kit():
    macros = templates.env.get_template("_macros.html").module
    empty = [
        name
        for name in sorted(set(_ADMIN_NAV_ICONS.values()))
        if not re.search(r"<(path|rect|circle|polyline|line)\b", str(macros.icon(name)))
    ]
    assert len(set(_ADMIN_NAV_ICONS.values())) >= 13, "the gate reads the icons"
    assert not empty, f"icons the kit does not have (an empty rail button): {empty}"


def test_the_design_system_page_names_the_admin_values():
    """Point 5 of #1482: the page's token list names the admin shell's values.

    It read `body[data-shell="admin"]` with the quotes, which the minifier
    drops, so it found nothing and showed the base values. Red on that version:
    `primary` came out as the base blue, not marked as the admin's.
    """
    from app.ui.design_system_ui import _radii, _tokens

    tokens = {naam: (waarde, schil) for naam, waarde, schil in _tokens()}
    assert tokens.get("primary") == ("#254e73", True), tokens.get("primary")
    assert not [n for n in tokens if n.startswith("c-gray-")], "a scale's shades stay off the page"
    assert dict(_radii()) == {"r-lg": "6px", "r-xl": "10px", "r-2xl": "10px"}
