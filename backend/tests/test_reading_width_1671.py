"""The reading width of a document page (CR-17 #1671, slice 4; C6 11).

What this pins at the source level — the browser measures the rest in
`tests_e2e/test_reading_width_1671.py`:

- the page template asks for the reading column (`doc-page`) and styles her
  body with the ONE prose class (`prose-raak`) — a screen sets no width of
  her own;
- the shells carry no hand-written prose rules any more: both carried
  near-identical `.cms-content` sets, two places for one fact, and the one
  source is `scripts/build-css.sh` now;
- the kit knows the container (1 024 px, centred, C4.13 "Where the width
  lives") with the text line at 768 px inside her, and the table's holder
  scrolling — the rules exist and say what the norm says.

Every test here can go red: drop the class from the template, put a rule
back in a shell, or delete a rule from the kit, and they fall over.
"""

import re
from pathlib import Path

APP = Path(__file__).resolve().parents[1] / "app"
BUILD = Path(__file__).resolve().parents[2] / "scripts" / "build-css.sh"


def test_the_page_template_asks_for_the_reading_column():
    """The page's whole column — title, document, contact — is the document
    page's: `doc-page`, the container of C4.13 ("Where the width lives");
    her body carries the ONE prose class. A screen sets no width of her own
    (the kit does)."""
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


def test_the_kit_knows_the_container_the_text_line_and_the_holders_scroll():
    """Phase 2, #1679 (the master CLI's comment of 11 October 2026 is the
    source until C4.13's paragraph stands on `master`): ONE container of
    1 024 px, CENTRED — the reading column of slice 4 sat on the shell's
    left edge and deviated from her own issue; the text runs to at most
    768 px, capped WITHOUT naming element types (everything direct child
    is narrow but the blocks C4.13 names wide), and a table stays a table
    at every width while WHAT HOLDS HER scrolls (`.prose-raak` herself —
    the page's container, the home intro, the newsletter archive).
    Proven red while building: taking the centring out (margin gone) made
    the container pin fall over on her left edge."""
    css = (APP / "static" / "app.css").read_text()
    doc_page = re.search(r"\.doc-page\{[^}]*\}", css)
    assert doc_page is not None, "the reading column is gone"
    assert "max-width:1024px" in doc_page.group(0), "the container is not 1 024 px"
    assert "width:100%" in doc_page.group(0), "the container no longer fills her frame"
    assert "margin-left:auto" in doc_page.group(0), "the container is not centred"
    build = BUILD.read_text()
    assert (
        ".doc-page .prose-raak>*:not(table):not(.prose-figure--full){max-width:768px}" in build
    ), "the text line is gone or names element types"
    assert ".prose-raak{overflow-x:auto}" in build, "a table's holder cannot scroll"
    assert "width:max-content" not in build.split(".prose-raak table")[1].split("}")[0], (
        "the table is a block, not a table"
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
