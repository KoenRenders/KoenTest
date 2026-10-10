"""#1287 — one product row for registering, adding and editing; a counter everywhere.

There were two rows with their own markup, and they drifted: the edit screen had a
line amount and a `type="number"` field (browser arrows, invisible on iOS), the
registration form had the counter and no line amount. Koen decided (28 September
2026): the counter everywhere, the line amount nowhere. The row now lives once, in
`activities/templates/_product_row.html`, and this gate keeps it the only one:

- no `type="number"` in `activities/templates` — outside Jinja comments, which
  may explain why there is none;
- the counter only in `_product_row.html`, and only as the kit's `ui.quantity(`
  (CR-21 phase 0, #1748: the counter of a quantity lives in the kit, so the
  webshop counts with the same one): a second, hand-written row with its own
  counter — `ui.quantity(` or the bare `ui.stepper(` — fails here with its file;
- the registration price block and the edit panel both call `rows.product_row(`.

Proven red (29 September 2026), additively:
- a `{{ ui.input_control("quantity", type="number") }}` added to
  `_inschrijving_detail.html` → "type=number in activities/templates";
- a `{{ ui.stepper("x") }}` added to `_inschrijf_prijsblok.html` → "a counter
  outside the one product row";
- the scan pointed at a folder that does not exist → `bestanden()`, "0 bestanden".

Proven red again with the move (8 October 2026): `ui.quantity(` in the row put back
to `ui.stepper(` → "a bare stepper in activities/templates"; a `{{ ui.quantity("x",
"x", 0) }}` added to `_inschrijf_prijsblok.html` → "a counter outside the one
product row"; the `quantity` macro taken out of `_macros.html` → "the kit lost".
"""

import re
from pathlib import Path

import pytest

from tests._bestanden import bestanden

pytestmark = pytest.mark.ui_agnostisch

TEMPLATES = Path(__file__).resolve().parents[1] / "app" / "domains" / "activities" / "templates"
ROW = "_product_row.html"
COMMENT = re.compile(r"\{#.*?#\}", re.S)


def _sources() -> dict[str, str]:
    files = bestanden(TEMPLATES.glob("*.html"), wat="activities/templates/*.html", minstens=10)
    return {p.name: COMMENT.sub("", p.read_text(encoding="utf-8")) for p in files}


def test_no_number_field_in_the_activity_templates():
    found = {name for name, src in _sources().items() if re.search(r"type=[\"']number", src)}
    assert not found, f"type=number in activities/templates — use ui.quantity: {sorted(found)}"


def test_the_counter_lives_only_in_the_one_product_row():
    sources = _sources()
    bare = {n for n, src in sources.items() if "ui.stepper(" in src}
    assert not bare, f"a bare stepper in activities/templates — use ui.quantity: {sorted(bare)}"
    outside = {n for n, src in sources.items() if "ui.quantity(" in src and n != ROW}
    assert not outside, f"a counter outside the one product row ({ROW}): {sorted(outside)}"
    assert "ui.quantity(" in sources[ROW], "the product row lost its counter"
    kit = COMMENT.sub("", (TEMPLATES.parents[2] / "ui" / "templates" / "_macros.html").read_text())
    assert "{% macro quantity(" in kit, "the kit lost the counter of a quantity"


@pytest.mark.parametrize("template", ["_inschrijf_prijsblok.html", "_inschrijving_detail.html"])
def test_both_screens_use_the_one_row(template):
    assert "rows.product_row(" in _sources()[template], f"{template} writes its own product row"


def test_the_total_line_comes_from_the_kit():
    """CR-21 phase 0 (#1748): the total under counted things is the kit's
    `ui.total_line`, so the webshop's basket reads as a registration does.

    Proven red: a hand-written `<div data-total>` added to `_inschrijf_prijsblok.html`
    → "a total line written by hand"; `ui.total_line(` taken out of
    `_inschrijf_totaal.html` → "the registration form's total left the kit"; a
    `cls="justify-end"` added to the edit screen's call → "restyles it"; an
    `align=""` parameter added to the macro → "got a switch".
    """
    sources = _sources()
    by_hand = {n for n, src in sources.items() if re.search(r"data-total\b", src)}
    assert not by_hand, f"a total line written by hand — use ui.total_line: {sorted(by_hand)}"
    assert "ui.total_line(" in sources["_inschrijf_totaal.html"], (
        "the registration form's total left the kit"
    )
    # One look, no switch (Koen, 8 October 2026): the edit screen's total is the
    # same line, called with the amount and its hook and nothing that restyles it.
    assert (
        'ui.total_line(totaal, attrs="data-registration-total")'
        in sources["_inschrijving_totaal.html"]
    ), "the edit screen's total left the kit, or restyles it"
    kit = COMMENT.sub("", (TEMPLATES.parents[2] / "ui" / "templates" / "_macros.html").read_text())
    assert '{% macro total_line(amount, note="", attrs="") -%}' in kit, (
        "the kit's total line got a switch — it has one look"
    )
