"""#1287 — one product row for registering, adding and editing; a counter everywhere.

There were two rows with their own markup, and they drifted: the edit screen had a
line amount and a `type="number"` field (browser arrows, invisible on iOS), the
registration form had the counter and no line amount. Koen decided (28 September
2026): the counter everywhere, the line amount nowhere. The row now lives once, in
`activities/templates/_product_row.html`, and this gate keeps it the only one:

- no `type="number"` in `activities/templates` — outside Jinja comments, which
  may explain why there is none;
- `ui.stepper(` only in `_product_row.html`: a second, hand-written row with its
  own counter fails here with its file;
- the registration price block and the edit panel both call `rows.product_row(`.

Proven red (29 September 2026), additively:
- a `{{ ui.input_control("quantity", type="number") }}` added to
  `_inschrijving_detail.html` → "type=number in activities/templates";
- a `{{ ui.stepper("x") }}` added to `_inschrijf_prijsblok.html` → "a counter
  outside the one product row";
- the scan pointed at a folder that does not exist → `bestanden()`, "0 bestanden".
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
    assert not found, f"type=number in activities/templates — use rows.quantity: {sorted(found)}"


def test_the_counter_lives_only_in_the_one_product_row():
    outside = {n for n, src in _sources().items() if "ui.stepper(" in src and n != ROW}
    assert not outside, f"a counter outside the one product row ({ROW}): {sorted(outside)}"
    assert "ui.stepper(" in _sources()[ROW], "the product row lost its counter"


@pytest.mark.parametrize("template", ["_inschrijf_prijsblok.html", "_inschrijving_detail.html"])
def test_both_screens_use_the_one_row(template):
    assert "rows.product_row(" in _sources()[template], f"{template} writes its own product row"
