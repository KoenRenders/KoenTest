"""#1546 — the site names itself through one resolver, never by reading a name.

`kernel.tenant_config.tenant_display_name` decides a site's name: its own "Naam
van de site", else the name of the organisation behind it (#1550). The public
templates show it as `site_name` / `site_wordmark`. A template that put an
organisation's `.name` in a place where the site names itself — the tab title,
`og:site_name`, the JSON-LD name — would bypass the resolver and show the legal
name where the site's name belongs.

#1616 (Koen, 5 October 2026) turned the rule of the "©" line around: the legal
line names the ORGANISATION behind the site, through its own resolver
(`legal_name`, from `tenant_config.site_name_default`). It must read that
variable; it may not read `site_name`, and it may not read a `.name` either —
which row is behind the site (#1550) is the resolver's to decide.

The organisation block in the footer shows the organisation's legal name on
purpose (`organisatie.name`): it is not a place where the site names itself, and
none of the markers below stands on its line. Admin templates are left out:
their titles name the record being edited, not the site.

Proven red: `test_the_check_finds_a_name_read_where_the_site_names_itself` feeds
the checker a template line with `{{ organisatie.name }}` in a `<title>` and
expects it caught; `test_the_legal_line_names_the_organisation` feeds it a "©"
line with `{{ site_name }}`, one with `{{ org.name }}` and one with no name at
all, and expects each caught.
"""

from __future__ import annotations

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"

#: Where a site names itself.
MARKERS = re.compile(r"<title>|\{% block title %\}|og:site_name|©|\"@type\":\"Organization\"")
#: The legal line (#1616): it names the organisation, through `legal_name`.
LEGAL_LINE = re.compile(r"©")
LEGAL_NAME = re.compile(r"\{\{\s*legal_name\s*\}\}")
SITE_NAME = re.compile(r"\b(site_name|site_wordmark)\b")
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
        if MARKERS.search(line)
        and (
            NAME_READ.search(line)
            or (LEGAL_LINE.search(line) and (SITE_NAME.search(line) or not LEGAL_NAME.search(line)))
            or (not LEGAL_LINE.search(line) and LEGAL_NAME.search(line))
        )
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
    # #1616: the shell's legal line was seen, so the turned rule looked at it.
    legal = [
        line
        for p in templates
        for line in p.read_text().splitlines()
        if LEGAL_LINE.search(line) and "{{" in line
    ]
    assert len(legal) == 1, f"expected the shell's one legal line, found {len(legal)}"


def test_the_check_finds_a_name_read_where_the_site_names_itself():
    assert violations("<title>{{ organisatie.name }}</title>")
    assert violations("<p>© {{ current_year }} {{ org.name }}</p>")
    assert not violations('<p class="font-semibold">{{ organisatie.name }}</p>'), (
        "the footer's organisation block is not a place where the site names itself"
    )
    assert not violations("<title>{{ site_name }}</title>")


def test_the_legal_line_names_the_organisation():
    """#1616. Proven red on the real template too: `{{ legal_name }}` put back
    to `{{ site_name }}` in `site_base.html` fails the gate above with that
    line."""
    assert not violations("<p>© {{ current_year }} {{ legal_name }}</p>")
    assert violations("<p>© {{ current_year }} {{ site_name }}</p>"), "the site's name"
    assert violations("<p>© {{ current_year }} {{ org.name }}</p>"), "a name read directly"
    assert violations("<p>© {{ current_year }}</p>"), "no name at all"
    assert violations("<title>{{ legal_name }}</title>"), (
        "the legal name where the site names itself"
    )
