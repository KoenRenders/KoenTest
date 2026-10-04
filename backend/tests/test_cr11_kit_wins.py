"""CR-11 phase 1, the kit and shell quick wins (#1391): W10, W5, W9 and W16.

Each test pins what the issue measures. The 390 px geometry itself (the create
button on the title line, inside the gutter) was measured in a browser for the
handover; here the markup that produces it is pinned, so a later edit of the
macro fails in CI rather than on a phone.
"""

import html as html_module
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


def test_a_list_page_keeps_its_create_button_beside_the_title_on_a_phone():
    """W10, now only for a list page (`list_page=True`): below md the action
    wrapper dissolves and every action but the LAST — the create button — moves
    to the row under the title; the title truncates. Drop the `order-1` or the
    `truncate` and this goes red."""
    html = _render(
        "{% call ui.page_header('Nieuwsbrieven', 'Uitleg', list_page=True) %}"
        "<a>Instellingen</a><a>Abonnees</a><a>+ Nieuwe nieuwsbrief</a>{% endcall %}"
    )
    h1 = _element(html, "<h1", "h1")
    assert "truncate" in h1 and "min-w-0" in h1
    header = _element(html, "<div data-page-header")
    # The class is written by an expression, so the attribute arrives escaped
    # (`&amp;&gt;`); a browser decodes it, and so does this test.
    actions = html_module.unescape(_element(header, "<div data-header-actions"))
    assert "contents [&>*:not(:last-child)]:order-1" in actions
    assert "md:[&>*:not(:last-child)]:order-none" in actions, "desktop keeps the DOM order"
    assert actions.index("Abonnees") < actions.index("+ Nieuwe nieuwsbrief")
    # The subtitle leaves the title column on a phone: full width, under both.
    assert "basis-full" in _element(header, "<p", "p")


def test_any_other_header_gives_the_title_its_line_and_drops_the_actions():
    """Koen on HDEV, 1 October 2026: W10 squeezed the meeting's title into
    "Verg… — zondag 1 nove…" beside five buttons. By default the title block's
    natural width is the title on one line (the subtitle does not count:
    `w-0 min-w-full`), it never shrinks (`flex-[1_0_auto]`), and the actions sit
    in a wrapping row that drops under it when both do not fit (`ml-auto`). No
    W10 machinery: nothing dissolves, nothing is reordered. Proven red against
    master 8c010f5c, where the header was a grid with the actions in an `auto`
    column beside a `minmax(0,1fr)` title."""
    html = _render(
        "{% call ui.page_header('Vergadering — zondag 1 november 2026', 'Uitleg') %}"
        "<a>A</a><a>B</a><a>C</a><a>D</a><a>E</a>{% endcall %}"
    )
    header = _element(html, "<div data-page-header")
    assert "md:grid" not in header and "flex flex-wrap" in header
    block = _element(header, "<div data-title-block")
    assert "flex-[1_0_auto]" in block and "max-w-full" in block and "contents" not in block
    assert "w-0 min-w-full" in _element(block, "<p", "p"), "the subtitle widens the block"
    assert "truncate" in _element(block, "<h1", "h1"), "one line, never word by word"
    actions = _element(header, "<div data-header-actions")
    assert "ml-auto" in actions and "flex-wrap" in actions and "order-1" not in actions


def test_an_empty_call_block_is_no_actions():
    """A screen with nothing in its call block (Organisaties since W5) gets no
    empty action wrapper, and a list page without actions no W10 machinery."""
    for body in (
        "{% call ui.page_header('Organisaties') %}{% endcall %}",
        "{{ ui.page_header('Organisaties') }}",
        "{% call ui.page_header('Organisaties', list_page=True) %}{% endcall %}",
    ):
        html = _render(body)
        assert "data-header-actions" not in html and "contents" not in html, body


def test_the_list_pages_are_the_headers_with_a_create_button():
    """`list_page=True` exactly where the call block carries a "+ …" create
    button: the W10 rule is for list pages, and that button is how one is
    recognised. A new list page that forgets the flag, or a record page that
    takes it, fails here."""
    import re

    scanned = 0
    wrong = []
    for path in APP.rglob("*.html"):
        text = path.read_text()
        for m in re.finditer(r"\{% call ui\.page_header\((.*?)\{% endcall %\}", text, re.S):
            scanned += 1
            call = m.group(0)
            head = call[: call.index("%}")]
            has_create = bool(re.search(r"""["']\+ """, call))
            if has_create != ("list_page=True" in head):
                wrong.append(str(path.relative_to(APP)))
    assert scanned > 20, f"the scan found only {scanned} headers"
    assert not wrong, wrong


# ── W5: no header button that only repeats the menu ──────────────────────────


def test_the_organisations_header_links_to_no_other_module(client, platform_workspace, db_session):
    _login(client)
    html = client.get("/admin/organisaties").text
    header = _element(html, "<div data-page-header")
    assert "Organisaties" in header, "the measurement found the wrong header"
    # #1495: "+ Nieuw account" is the screen's own primary action, not a link to
    # another module — what this test is about.
    links = re.findall(r'href="([^"]*)"', header)
    assert all(link.startswith("/admin/organisaties") for link in links), links
    assert "Naar de tenants" not in html


def test_the_reports_header_links_to_no_other_module(client, db_session):
    """Until #1562 this measured the header of the assistant's own page, which
    had lost its "Naar de rapporten" button. That page is gone — its address
    moves to the reports list for good — and the list lost its "AI · Raakje"
    button with it: the header there holds the list's own action and no link
    to another screen."""
    _login(client)
    moved = client.get("/admin/rapporten/raakje", follow_redirects=False)
    assert moved.status_code == 301 and moved.headers["location"] == "/admin/rapporten"

    html = client.get("/admin/rapporten").text
    header = _element(html, "<div data-page-header")
    assert "Nieuw rapport" in header, "the measurement found the wrong header"
    links = re.findall(r'href="([^"]*)"', header)
    assert links == ["/admin/rapporten/nieuw"], links
    assert "AI · Raakje" not in html and "Naar de rapporten" not in html


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

# The activity's three pages left this list with #1557: their way back is drawn
# by `ui.record_header`, and `test_record_header_gate.py` pins that the head is
# the first thing they render.
RECORD_PAGES = [
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


# ── W12 follow-up: tile numbers on one line ──────────────────────────────────


def test_every_tile_strip_keeps_its_labels_on_one_line_through_the_shared_rule():
    """#1426 lined the numbers up with a subgrid, which made every short label's
    tile as tall as the long one (Koen, 1 October 2026, #1432). Now a label is
    one line — "…" and a `title` when too long — so every number sits right
    under its label at the same height. One rule (`.kpi-strip`) in the shared
    stylesheet; every strip carries the class, every label a `title`. Proven
    red by dropping the class from `admin_activiteiten.html`, by deleting the
    rule, and by dropping a label's `title`."""
    strip = "md:flex-row rounded-card border border-gray-200 bg-white shadow-sm divide-y md:divide-y-0 md:divide-x divide-gray-100"
    found = []
    for path in APP.rglob("*.html"):
        lines = path.read_text().splitlines()
        for i, line in enumerate(lines):
            if strip in line:
                found.append(path.relative_to(APP))
                assert "kpi-strip" in line, f"{path.relative_to(APP)}: no kpi-strip"
                # Each tile's first child is its label; each carries a title.
                tiles = [
                    lines[j + 1]
                    for j in range(i + 1, len(lines))
                    if lines[j].lstrip().startswith('<div class="flex-1')
                    and lines[j].startswith("  <div")
                ]
                labels = [t for t in tiles if "text-ink-soft" in t]
                assert labels, f"{path.relative_to(APP)}: the scan found no labels"
                for label in labels:
                    assert "title=" in label, f"{path.relative_to(APP)}: a label without a title"
    assert len(found) >= 3, f"the scan found only {found}"
    css = (APP / "static" / "app.css").read_text()
    assert ".kpi-strip>*>:first-child{" in css
    rule = css[css.index(".kpi-strip>*>:first-child{") :]
    rule = rule[: rule.index("}")]
    assert "nowrap" in rule and "ellipsis" in rule
    assert "subgrid" not in css, "the subgrid of #1426 is back"
