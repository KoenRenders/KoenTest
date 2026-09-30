"""Both admin menus take their account items from one partial (#1381).

The desktop account menu and the mobile menu behind the hamburger load
`_account_menu.html` from `/admin/accountmenu`, and show the same partial as a
fallback until that swap. A second list of account links in the shell would drift
from the first: "Werkruimte wisselen" was added to the partial in #963 and never
reached the mobile menu, which kept its own "Uitloggen".

Proven red with an additive violation: a "Mijn profiel" link added to the mobile
menu of `admin_base.html` fails the first test; on master `08a3ffbd` the second
test fails, since the mobile menu did not load the partial.
"""

from __future__ import annotations

import re
from pathlib import Path

TEMPLATES = Path(__file__).resolve().parents[1] / "app" / "ui" / "templates"
SHELL = TEMPLATES / "admin_base.html"
PARTIAL = TEMPLATES / "_account_menu.html"


def test_the_account_links_live_only_in_the_partial():
    shell = SHELL.read_text()
    partial = PARTIAL.read_text()
    assert 'href="/admin/profiel"' in partial and "/admin/werkruimte-wisselen" in partial
    for link in ('href="/admin/profiel"', "/admin/werkruimte-wisselen"):
        assert link not in shell, f"{link} is listed in the shell next to the partial"


def test_both_menus_load_the_partial():
    shell = SHELL.read_text()
    mobile = re.search(r'<nav id="admin-nav-mobiel".*?</nav>', shell, re.S)
    assert mobile, "the mobile menu was not found"
    desktop = shell[mobile.end() :]
    for name, part in (("mobile", mobile.group(0)), ("desktop", desktop)):
        assert 'hx-get="/admin/accountmenu"' in part, f"the {name} menu does not load the items"
        assert '{% include "_account_menu.html" %}' in part, f"the {name} menu has its own fallback"
