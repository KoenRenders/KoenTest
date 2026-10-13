"""Read mode keeps the edit grid (#1928; end state §2.2, CR-11 Q98).

Koen, 12 October 2026: "ik zou bij deze willen dat het bewerkscherm leidend is"
and "gelieve de lijnafstand tussen de velden gelijk te zetten aan gezin en aan
de personen daar … consistent over al de schermen heen". So a record's facts
stand in the cells of the form grid, and the kit — not the screen — sets the
rows apart: 4 px in read mode, the person card's gap.

Two rules:

- the stylesheet gives the form grid of a read-mode flow a row gap of 4 px;
- a template of a record that reads and edits (a form flow whose mode follows
  the page) stacks no facts with a distance of its own: no `flex-col` with a
  `gap-y-*`, no `space-y-*`.

Proven red (13 October 2026, each put back): the rule taken out of
`scripts/build-css.sh` and the css rebuilt → the first test; the booking's
facts put back in `flex flex-col gap-y-1` → the second names the file and line.
"""

from __future__ import annotations

import re
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"
CSS = APP / "static" / "app.css"

#: A form flow whose mode is the page's: the record reads and edits.
_BOTH_MODES = 'data-form-flow data-mode="{{'
_OWN_DISTANCE = re.compile(r'class="[^"]*(?:flex-col[^"]*\bgap-y-|\bspace-y-)[^"]*"')


def _record_templates() -> dict[str, str]:
    found = {}
    for path in sorted(APP.rglob("templates/*.html")):
        text = path.read_text()
        if _BOTH_MODES in text:
            found[str(path.relative_to(APP))] = text
    return found


def own_distances(rel: str, text: str) -> list[str]:
    return [
        f"{rel}:{number}: {line.strip()[:90]}"
        for number, line in enumerate(text.splitlines(), 1)
        if _OWN_DISTANCE.search(line)
    ]


def test_the_read_grid_has_four_pixels_between_its_rows():
    css = CSS.read_text()
    assert re.search(r"\.form-grid\{[^}]*display:grid", css), "the form grid's own rule is gone"
    # the build drops the quotes of an attribute value
    assert re.search(r'\.form-flow\[data-mode="?read"?\] \.form-grid\{row-gap:4px\}', css), (
        "read mode keeps the edit grid with 4 px between its rows (#1928) — "
        "the rule is not in the built stylesheet"
    )


def test_a_record_template_sets_no_distance_between_facts_itself():
    templates = _record_templates()
    assert len(templates) >= 5, f"only {len(templates)} record templates found: {list(templates)}"
    assert any("_aa_detail.html" in rel for rel in templates)
    assert any("_bt_boeking.html" in rel for rel in templates)
    wrong = [hit for rel, text in templates.items() for hit in own_distances(rel, text)]
    assert not wrong, (
        "a fact stands in a cell of the form grid, which sets the rows apart (#1928):\n"
        + "\n".join(wrong)
    )


def test_a_stack_with_its_own_gap_is_red_and_a_wrapping_line_is_not():
    stacked = '<div data-facts class="flex flex-col gap-y-1 text-sm">'
    spaced = '<div class="space-y-2">'
    wrapping = '<p class="flex flex-wrap gap-x-5 gap-y-1 text-sm">'
    assert own_distances("x.html", stacked) and own_distances("x.html", spaced)
    assert not own_distances("x.html", wrapping)
