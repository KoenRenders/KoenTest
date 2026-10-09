"""The reading width of a document page (CR-17 #1671, slice 4; C6 11).

What this pins at the source level — the browser measures the rest in
`tests_e2e/test_reading_width_1671.py`:

- the page template asks for the reading column (`doc-page`) and styles her
  body with the ONE prose class (`prose-raak`) — a screen sets no width of
  her own;
- the shells carry no hand-written prose rules any more: both carried
  near-identical `.cms-content` sets, two places for one fact, and the one
  source is `scripts/build-css.sh` now;
- the kit knows the reading column (768 px, left-aligned) and the phone's
  table escape (her block scrolls inside itself) — the rules exist and
  say what the norm says.

Every test here can go red: drop the class from the template, put a rule
back in a shell, or delete a rule from the kit, and they fall over.
"""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
BUILD = Path(__file__).resolve().parents[2] / "scripts" / "build-css.sh"


def test_the_page_template_asks_for_the_reading_column():
    """The page's whole column — title, document, contact — is the document
    page's: `doc-page`, 768 px, left-aligned; her body carries the ONE prose
    class. A screen sets no width of her own (the kit does)."""
    pagina = (APP / "domains" / "cms" / "templates" / "cms_pagina.html").read_text()
    assert 'class="doc-page"' in pagina, "the page has no reading column"
    assert 'class="prose-raak cms-page"' in pagina, "the page body lost her prose class"


def test_the_shells_carry_no_hand_written_prose_rules():
    """One source: the prose rules live in `scripts/build-css.sh` under
    `.prose-raak`; the shells' <style> blocks hold nothing of them any more
    (site_base carried the public set, admin_base a near-copy for the
    preview — two places for one fact). A comment may NAME the class; a
    rule may not stand here."""
    for shell in ("site_base.html", "admin_base.html"):
        html = (APP / "ui" / "templates" / shell).read_text()
        assert ".cms-content" not in html, f"{shell} still carries prose rules"
        assert not re.search(r"\.prose-raak[^{\n]*\{", html), f"{shell} carries kit rules by hand"


def test_the_kit_knows_the_reading_column_and_the_tables_escape():
    """`doc-page` is 768 px and never centred (design-system-end-state §1.4:
    left-aligned like a record page); a table on a phone scrolls inside her
    own block (CR-11 Q14's declared exception)."""
    css = (APP / "static" / "app.css").read_text()
    doc_page = re.search(r"\.doc-page\{[^}]*\}", css)
    assert doc_page is not None, "the reading column is gone"
    assert "max-width:768px" in doc_page.group(0), "the reading column is wider than 768 px"
    assert "width:100%" in doc_page.group(0), "the reading column no longer fills her frame"
    assert "margin-inline:auto" not in doc_page.group(0), "the reading column is centred"
    build = BUILD.read_text()
    assert "overflow-x:auto" in build and "width:max-content" in build, (
        "a phone's table cannot scroll inside her block"
    )


def test_the_record_form_grows_only_where_the_screen_asks_for_it():
    """Koen, 9 October 2026: "links houden, maar het scherm benutten" — his
    words were about the PAGE screen's form. The wide reading group
    (1 056 px, summary 300 beside her, left-aligned) is carried by
    `data-wide`, which only the page screen's template sets (the CI run
    of 9 October scoped her, #1770: an existing record — the activity —
    keeps master's width)."""
    build = BUILD.read_text()
    assert ".record-columns[data-wide]{grid-template-columns:minmax(0,1056px)}" in build, (
        "the wide group lost her own selector"
    )
    assert "minmax(0,768px)" in build.split(".record-columns{")[1].split("}")[0], (
        "the default record column grew beyond master's width"
    )
    record = (APP / "ui" / "templates" / "_macros.html").read_text()
    assert "wide=False" in record, "the macro grew every record"
    pagina = (APP / "domains" / "cms" / "templates" / "_cp_record.html").read_text()
    assert "wide=True" in pagina, "the page screen lost her wide group"
    activiteit = (APP / "domains" / "activities" / "templates" / "_aa_record.html").read_text()
    assert "wide" not in activiteit, "the activity record grew with the page"
    assert "margin-inline:auto" not in build.split(".record-columns{")[1].split("}")[0], (
        "the reading group is centred — she must stay left"
    )
