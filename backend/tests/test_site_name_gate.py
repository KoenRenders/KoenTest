"""#1546 — the site names itself through one resolver, never by reading a name.

`kernel.tenant_config.tenant_display_name` decides a site's name: its own "Naam
van de site", else the name of the organisation behind it (#1550). The public
templates show it as `site_name` / `site_wordmark`. A template that put an
organisation's `.name` in a place where the site names itself — the tab title,
`og:site_name`, the JSON-LD name, the "©" line — would bypass the resolver and
show the legal name where the site's name belongs.

The organisation block in the footer shows the organisation's legal name on
purpose (`organisatie.name`): it is not a place where the site names itself, and
none of the markers below stands on its line. Admin templates are left out:
their titles name the record being edited, not the site.

Proven red: `test_the_check_finds_a_name_read_where_the_site_names_itself` feeds
the checker a template line with `{{ organisatie.name }}` in a `<title>` and
expects it caught.
"""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

#: Where a site names itself.
MARKERS = re.compile(r"<title>|\{% block title %\}|og:site_name|©|\"@type\":\"Organization\"")
#: An organisation's (or tenant's) name read directly.
NAME_READ = re.compile(r"\b(organisatie|organization|org|unit|tenant|account)\.name\b")


def _public_templates() -> list[Path]:
    return [
        p
        for p in APP.rglob("templates/**/*.html")
        if not p.name.startswith("admin_") and "admin" not in p.parent.name
    ]


def violations(text: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if MARKERS.search(line) and NAME_READ.search(line)
    ]


def test_no_public_template_reads_a_name_where_the_site_names_itself():
    templates = _public_templates()
    assert len(templates) > 50, f"only {len(templates)} public templates — the gate is blind"
    marked = [
        p for p in templates if any(MARKERS.search(line) for line in p.read_text().splitlines())
    ]
    assert any(p.name == "site_base.html" for p in marked), "the shell's title line was not seen"
    found = {str(p.relative_to(APP)): v for p in templates if (v := violations(p.read_text()))}
    assert not found, f"the site's name read past the resolver (#1546): {found}"


def test_the_check_finds_a_name_read_where_the_site_names_itself():
    assert violations("<title>{{ organisatie.name }}</title>")
    assert violations("<p>© {{ current_year }} {{ org.name }}</p>")
    assert not violations('<p class="font-semibold">{{ organisatie.name }}</p>'), (
        "the footer's organisation block is not a place where the site names itself"
    )
    assert not violations("<title>{{ site_name }}</title>")
