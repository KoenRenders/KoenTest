"""The figure's placements: ONE set, everywhere (#1671, slice 3).

The heir of the Trix-size gate (#1230). That gate guarded that the page
editor showed the same image sizes as the public page — "je koos *klein*
en zag *groot*" was the bug it closed, through attribute-selector rules
in the page template next to `IMAGE_SIZES`. Slice 3 took Trix off the
page screen, and the parity moved to the document figure: the schema's
`FIGURE_PLACEMENTS` is the one set, and three things must speak her —
the CSS file the site AND the editor load (`prose-figures.css`, one
source so the author sees the placement the visitor gets), the dialog's
placement buttons (generated from the same tuple in `schema_for`), and
the renderer's class on the published page.

**Why a gate and not only a look.** The e2e measures that a floated
figure sits beside the text; that stays green when a fifth placement
joins the tuple and nobody writes her CSS rule or her dialog button.
Then an author picks a placement, sees no difference, and nobody notices
until a visitor reports it. The set lives in ONE place (`schema.py`);
this gate holds the other two against her.

Broken on purpose to check these tests can go red (measured):
- the rule for `--small` removed from `prose-figures.css` → "the css
  misses a rule for placement 'small'";
- a rule for an invented placement `huge` added → "the css has a rule
  for 'huge', which is not a placement in FIGURE_PLACEMENTS";
- the `prose-figures.css` link removed from `site_base.html` → "the
  site no longer loads the figure rules";
- `figure` removed from the sanitiser's allowlist → the renderer tests
  fail: the published page loses her placement class.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from app.domains.cms.render import render_cms_content, render_document
from app.domains.cms.schema import FIGURE_PLACEMENTS, schema_for

BACKEND = Path(__file__).resolve().parents[4]
APP = BACKEND / "app"
CSS = APP / "static" / "prose-figures.css"
SITE_SHELL = APP / "ui" / "templates" / "site_base.html"

#: Every placement rule the css names: `.prose-figure--<placement>`.
RULE = re.compile(r"\.prose-figure--([a-z]+)")


def _rules_in_css() -> set[str]:
    return set(RULE.findall(CSS.read_text(encoding="utf-8")))


def test_every_placement_has_a_rule_and_every_rule_a_placement():
    """`full` belongs here, unlike Trix' `vol`: the renderer always writes
    the class (no placement IS `full`), so `full` carries her own rule —
    there is no implicit default left to fall out of."""
    rules = _rules_in_css()
    assert rules, (
        "no placement rule found in prose-figures.css — does the file "
        "still exist, or did the notation change?"
    )
    missing = set(FIGURE_PLACEMENTS) - rules
    assert not missing, (
        "the css misses a rule for placement "
        + ", ".join(repr(p) for p in sorted(missing))
        + " — an author picks that placement and sees no difference"
    )
    too_many = rules - set(FIGURE_PLACEMENTS)
    assert not too_many, (
        "the css has a rule for "
        + ", ".join(repr(p) for p in sorted(too_many))
        + ", which is not a placement in FIGURE_PLACEMENTS"
    )


def test_the_site_loads_the_one_file():
    """The public shell links the figure rules (the visitor sees the
    placement the author chose); the editor macro links the same file
    (the author sees her) — one file, no second copy to drift. The
    macro's link stands in the B4 gate (test_document_editor_gate_1671.py).
    The check looks for the LINK line, not the file name: the shell's own
    comment names the file too, and a gate that a comment satisfies is no
    gate (measured — removing only the link left her green)."""
    links = [
        line.strip()
        for line in SITE_SHELL.read_text(encoding="utf-8").splitlines()
        if "<link" in line and "prose-figures.css" in line
    ]
    assert links, (
        "the site no longer links the figure rules — the visitor does not "
        "see the placement the author chose"
    )


def test_the_dialog_offers_the_same_placements():
    """The figure dialog's buttons come from `schema_for`, generated from
    the same tuple the validation accepts — not from a list of her own in
    a template (the third-copy lesson, #528)."""
    config = schema_for("page")
    figure = config.get("figure") or {}
    offered = [p["id"] for p in figure.get("placements", [])]
    assert offered == list(FIGURE_PLACEMENTS), (
        f"the dialog offers the placements from a second source: {offered}"
    )
    # The picture address is media's, not the browser's own (CR-15 §C4.6):
    # the editor builds her preview from the prefix, so a change of the
    # URL's shape stays inside media.
    assert figure.get("mediaUrl") == "/api/v1/media/"


@pytest.mark.parametrize("placement", FIGURE_PLACEMENTS)
def test_the_renderer_writes_the_placement_the_schema_knows(placement):
    """The published page carries the class of the chosen placement —
    measured on the output, which means the sanitiser keeps the wrapper
    (widened in this slice; slice 1's review E note, #1673)."""
    document = {
        "type": "doc",
        "content": [
            {
                "type": "figure",
                "attrs": {"media_id": 1, "alt": "Het lokaal", "placement": placement},
            }
        ],
    }
    html = render_document(document, None, on_page=True)
    assert f"prose-figure--{placement}" in html, (
        f"the renderer does not write the class of placement {placement!r}"
    )


def test_a_figure_without_placement_renders_full():
    """A figure without a placement (slice 1's migration) is `full` — the
    rule the renderer already promised; measured, not read."""
    document = {
        "type": "doc",
        "content": [{"type": "figure", "attrs": {"media_id": 1, "alt": "Het lokaal"}}],
    }
    assert "prose-figure--full" in render_document(document, None, on_page=True)


def test_the_published_caption_travels_with_her_figure():
    """The caption the author typed in the dialog is the visitor's too —
    the sanitiser keeps her words since the wrapper is allowed."""
    document = {
        "type": "doc",
        "content": [
            {
                "type": "figure",
                "attrs": {
                    "media_id": 1,
                    "alt": "Het lokaal",
                    "placement": "right",
                    "caption": "Ons lokaal aan de Schoolstraat",
                },
            }
        ],
    }
    assert "Ons lokaal aan de Schoolstraat" in render_document(document, None, on_page=True)


def test_a_trix_era_picture_keeps_her_own_measure():
    """The legacy pin of the sanitiser widening. A Trix-era figure wrapper
    survives the sanitiser since `figure` joined the allowlist; this is
    the measurement that her pixels did not move: the `<img>` keeps the
    size class the attachment carried (#1207), the wrapper carries the
    Trix classes and NOT `prose-figure` — so no placement rule matches
    her, and the wrapper matched no style before either."""
    content = (
        '<div><figure data-trix-attachment="{&quot;alt&quot;:&quot;Schermafdruk&quot;,'
        "&quot;contentType&quot;:&quot;image&quot;,&quot;size&quot;:&quot;half&quot;,"
        '&quot;url&quot;:&quot;/api/v1/media/7&quot;}" '
        'data-trix-content-type="image" class="attachment attachment--preview">'
        '<img src="/api/v1/media/7">'
        '<figcaption class="attachment__caption"></figcaption></figure></div>'
    )
    html = render_cms_content(content)
    assert 'class="cms-beeld-half"' in html, f"the size class left the img:\n{html}"
    assert "attachment--preview" in html, "the Trix wrapper changed class"
    assert "prose-figure" not in html, "a Trix figure is not a placed figure"
    assert 'alt="Schermafdruk"' in html, "the alt of #1173 was lost"
