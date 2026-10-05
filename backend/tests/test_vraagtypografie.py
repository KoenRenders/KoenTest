"""A question on a public form has the anatomy of every other field (#1589).

#749 gave a question a heavier label of its own (`ui.vraag`, 16 px semibold)
under an 18 px bold section title, with a rhythm of its own between the
questions (`space-y-[22px]`), and #741 reserved a gutter at the left of every
question for a red error bar. CR-11 pilot B (Koen, 4 October 2026; decision 12,
`docs/design-system-end-state.md` §2.6) decided one label style for every field,
admin and public: **14 px medium, in ink** — "labels overal 14 px medium (geen
tweede labelstijl)" — in the kit's section cards (head Inter 16 px semibold),
the fields 12 px apart on the form grid, and a refused question marked like any
refused field: red border, its reason under it.

What #749 was about is kept by the kit: the label is in INK (the old `ui.label`
was mid grey, under answers that were almost black).

**These tests pin the structure, not the look.** The sizes as rendered stand in
`tests_e2e/test_public_form_page.py` (one label style measured on every label of
the page) and `tests_e2e/test_formulier_afstanden.py`.

Proven red: the label of a choice in `_formulier_veld.html` given
`class="text-base font-semibold"` → the first test fails (a second label
style); `data-field="{{ key }}"` taken off the choice block → the third test
fails.
"""

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.ui_serverrendered

MACROS = (Path(__file__).resolve().parents[1] / "app/ui/templates/_macros.html").read_text()
_FORMS = Path(__file__).resolve().parents[1] / "app/domains/forms/templates"
FIELD = (_FORMS / "_formulier_veld.html").read_text()
CARDS = (_FORMS / "_formulier_vragen.html").read_text()

#: The one label style: what `ui.field` gives a label.
LABEL = "text-sm font-medium leading-[21px] text-ink mb-1"


def test_there_is_one_label_style():
    """A question's label is the kit's: no macro and no class of its own."""
    assert "{% macro vraag(" not in MACROS, "the heavier question label is back"
    assert MACROS.count(f'class="block {LABEL}"') >= 1, "the kit's label changed: update LABEL"
    # A text, a long text, a number and a list ARE the kit's field.
    assert len(re.findall(r"ui\.field\(key, f\.label", FIELD)) == 4
    # A choice, several and a scale write their label with the same classes.
    assert f'{{% set _label = "{LABEL}" %}}' in FIELD
    assert FIELD.count('class="{{ _label }}"') == 1
    for heavier in ("text-base font-semibold", "font-bold", "text-lg"):
        assert heavier not in FIELD, f"a second label style: {heavier}"


def test_the_cards_are_the_kits_sections():
    """One card per section with the section's title as its head, the questions on
    the form grid — the template writes no distance of its own."""
    assert CARDS.count("{% call ui.section(") == 2, "a card per section, and one for loose fields"
    assert "ui.section(g.section.title, intro=g.section.description" in CARDS
    assert "<section" not in CARDS and "<h2" not in CARDS, "a card written by hand"
    assert "space-y-" not in CARDS and "space-y-" not in FIELD, "a rhythm beside the grid's"
    assert "ui.card(" not in CARDS, "a card of the old kit inside the flow"


def test_a_refused_question_is_marked_like_any_field():
    """Every question is a `data-field` named `f<id>`: the banner names it and
    `record-form.js` marks it. No gutter reserved for a bar of its own (#741)."""
    assert 'data-field="{{ key }}"' in FIELD, "a choice is not a field the banner can name"
    for trace in ("border-l-4", "-ml-4", "data-veld"):
        assert trace not in FIELD, f"the old error gutter: {trace}"


def test_an_answer_row_is_as_high_as_a_control():
    """#768: the target of an answer is the whole row, and the rows touch — no
    strip between two answers where a tap does nothing. Since #1589 a row has the
    kit's size: 44 px on a phone, 40 above."""
    assert (
        '{% set _row = "flex flex-wrap items-center gap-2 min-h-11 md:min-h-10 '
        'text-sm text-ink cursor-pointer" %}' in FIELD
    )
    assert FIELD.count('<label class="{{ _row }}">') == 1, "radio and checkbox share one row"
    group = FIELD[FIELD.index("role=\"{{ 'radiogroup' if f.kind.is_radio") :]
    assert 'class="grid"' in group[:200], "the rows of a group no longer touch"
    assert "-my-" not in FIELD, "negative margins make the targets overlap"
