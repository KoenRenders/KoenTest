"""CR-11 phase 1, the kit and shell quick wins (#1391): W10, W5, W9 and W16.

Each test pins what the issue measures. The 390 px geometry itself (the create
button on the title line, inside the gutter) was measured in a browser for the
handover; here the markup that produces it is pinned, so a later edit of the
macro fails in CI rather than on a phone.
"""

import re
from pathlib import Path

from app.domains.auth.api import SESSION_COOKIE, make_session_value
from app.ui import templates
from tests.conftest import SEEDED_ADMIN_EMAIL

APP = Path(__file__).resolve().parents[1] / "app"


def _login(client):
    client.cookies.set(SESSION_COOKIE, make_session_value(SEEDED_ADMIN_EMAIL))


def _render(body: str) -> str:
    return templates.env.from_string("{% import '_macros.html' as ui %}" + body).render()


def _element(html: str, start: str, tag: str = "div") -> str:
    """The element that opens at `start`, up to its own closing tag."""
    begin = html.index(start)
    depth = 0
    for m in re.finditer(rf"<{tag}\b|</{tag}>", html[begin:]):
        depth += 1 if m.group(0) != f"</{tag}>" else -1
        if depth == 0:
            return html[begin : begin + m.end()]
    raise AssertionError(f"{start!r} is never closed")


# ── W10: the create button stays on the title line ──────────────────────────


def test_a_header_with_actions_truncates_its_title_and_keeps_the_last_action_on_top():
    """Below md the action wrapper dissolves and every action but the LAST — the
    primary — moves to the row under the title; the title yields by truncating.
    Drop the `order-1` on the secondary actions or the `truncate` and this goes
    red."""
    html = _render(
        "{% call ui.page_header('Nieuwsbrieven', 'Uitleg') %}"
        "<a>Instellingen</a><a>Abonnees</a><a>+ Nieuwe nieuwsbrief</a>{% endcall %}"
    )
    h1 = _element(html, "<h1", "h1")
    assert "truncate" in h1 and "min-w-0" in h1 and "md:whitespace-normal" in h1
    header = _element(html, "<div data-page-header")
    actions = header[header.index("</h1>") :]
    assert "contents [&>*:not(:last-child)]:order-1" in actions
    assert "md:[&>*:not(:last-child)]:order-none" in actions, "desktop keeps the DOM order"
    assert actions.index("Abonnees") < actions.index("+ Nieuwe nieuwsbrief")
    # The subtitle leaves the title column on a phone: full width, under both.
    assert "basis-full" in _element(header, "<p", "p")


def test_an_empty_call_block_is_no_actions():
    """A screen with nothing in its call block (Organisaties since W5) gets a
    title that wraps as before and no empty action wrapper."""
    html = _render("{% call ui.page_header('Organisaties') %}{% endcall %}")
    assert "truncate" not in html and "contents" not in html
    bare = _render("{{ ui.page_header('Organisaties') }}")
    assert "truncate" not in bare and "contents" not in bare


# ── W5: no header button that only repeats the menu ──────────────────────────


def test_the_organisations_header_links_to_no_other_module(client, db_session):
    _login(client)
    html = client.get("/admin/organisaties").text
    header = _element(html, "<div data-page-header")
    assert "Organisaties" in header, "the measurement found the wrong header"
    assert "href=" not in header and "Naar de tenants" not in html


def test_the_raakje_report_header_links_to_no_other_module(client, db_session):
    _login(client)
    html = client.get("/admin/rapporten/raakje").text
    header = _element(html, "<div data-page-header")
    assert "Raakje" in header, "the measurement found the wrong header"
    assert 'href="/admin/rapporten"' not in header and "Naar de rapporten" not in html


# ── W9: the account menu reads as a menu ─────────────────────────────────────


def test_the_account_trigger_shows_initials_and_a_chevron_not_the_address(client, db_session):
    _login(client)
    html = client.get("/admin/leden").text
    button = _element(html, '<button type="button" @click="acc = !acc"', "button")
    assert 'aria-haspopup="menu"' in button and "focus-visible:ring-2" in button
    assert SEEDED_ADMIN_EMAIL not in button, "the address is back in the bar"
    assert '<path d="m6 9 6 6 6-6"/>' in button, "no chevron"


def test_the_opened_menu_starts_with_who_is_signed_in(client, db_session):
    """Both the lazy fragment and the shell's fallback (the same template) open
    with "Aangemeld als <address>", above "Mijn profiel"."""
    _login(client)
    for html in (
        client.get("/admin/accountmenu").text,
        client.get("/admin/leden").text.split('hx-get="/admin/accountmenu"', 1)[1],
    ):
        assert "Aangemeld als" in html and SEEDED_ADMIN_EMAIL in html
        assert html.index("Aangemeld als") < html.index(SEEDED_ADMIN_EMAIL)
        assert html.index(SEEDED_ADMIN_EMAIL) < html.index("Mijn profiel")


# ── W16: every record page starts with the way back ──────────────────────────

RECORD_PAGES = [
    "domains/activities/templates/admin_activiteit.html",
    "domains/activities/templates/admin_activiteit_inschrijvingen.html",
    "domains/payment/templates/admin_activiteit_betalingen.html",
    "domains/mdm/templates/leden_gezin.html",
    "domains/mdm/templates/admin_gezin_inschrijvingen.html",
    "domains/payment/templates/admin_gezin_betalingen.html",
    "domains/cms/templates/admin_pagina.html",
    "domains/activities/templates/_insch_recordkop.html",
    "domains/forms/templates/_fb_recordkop.html",
    "domains/workflow/templates/werkbank_taak.html",
    "ui/templates/admin_tenant.html",
    "ui/templates/admin_organisatie.html",
    "domains/designstudio/templates/admin_ontwerp.html",
    "domains/reporting/templates/admin_rapport_paneel.html",
]


def _without_comments(text: str) -> str:
    return re.sub(r"\{#.*?#\}", "", text, flags=re.S)


def test_every_record_page_starts_with_the_back_link_macro():
    """The first thing a record page renders is `ui.back_link` — before the
    record header, whether that is a `page_header` call or an include. Skipped:
    comments, `{% import %}`, `{% set %}` and `<style>`/`<script>` blocks, which
    render nothing on the page. Proven red by moving the back link in
    admin_tenant.html below its page_header."""
    for rel in RECORD_PAGES:
        text = _without_comments((APP / rel).read_text())
        if "{% block content %}" in text:
            text = text.split("{% block content %}", 1)[1]
        text = re.sub(r"<(style|script)\b.*?</\1>", "", text, flags=re.S)
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip() and not line.strip().startswith(("{% import", "{% set", "{% extends"))
        ]
        assert lines[0].startswith("{{ ui.back_link("), f"{rel}: starts with {lines[0]!r}"


def test_no_admin_template_writes_the_left_arrow():
    """ "←" was the second spelling of the way back. Public pages keep theirs
    (the site shell is not the admin kit); the admin side has one spelling."""
    scanned = 0
    offenders = []
    for path in APP.rglob("*.html"):
        name = path.name
        if not (name.startswith(("admin_", "_", "leden", "werkbank")) or "admin" in name):
            continue
        scanned += 1
        if "←" in _without_comments(path.read_text()):
            offenders.append(str(path.relative_to(APP)))
    assert scanned > 100, f"the scan found only {scanned} templates"
    assert not offenders, offenders
