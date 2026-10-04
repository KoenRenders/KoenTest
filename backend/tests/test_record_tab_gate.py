"""CR-11 pilot A, K6 (#1560): what a record's tab may not do.

Block 8 (Koen, 4 October 2026; `docs/design-system-end-state.md` §2.2, §3.10):

1. **a summary card on a list tab** — the card stands on Gegevens only; a tab
   that holds a list (a table or a toolbar) starts directly under the tabs at
   the full width. A page whose template family renders both `ui.summary_card`
   and a list is red.
2. **anything that edits in an unfolded row** — the row unfolds read-only
   (Q42): no "Bewerken", no button, no form, no input inside `ui.row_detail`.
   Editing is the record page's; the unfolded row carries a jump link there.

The gate reads every page template and what it includes. It counts what it
read (`test_the_gate_reads_the_tabs_of_the_pilot`): a gate that finds nothing
is green for ever.

Proven red, additively — each rule on a throwaway template text that adds one
violation to a clean one (`test_every_rule_refuses_its_violation`).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"

_INCLUDE = re.compile(r'{%-?\s*include\s+"([^"]+)"')
_COMMENT = re.compile(r"{#.*?#}", re.S)
_LIST = re.compile(r"ui\.data_table\(|ui\.toolbar\(")
_CARD = re.compile(r"ui\.summary_card\(")
#: The kit's own demo page renders every macro on one page; it is no record tab.
SHOWS_EVERY_MACRO = {"design_system.html"}

_EDITS = re.compile(r"Bewerken|ui\.btn_|ui\.link_action|<button|<form|<input|<select|<textarea")


def _templates() -> dict[str, Path]:
    return {p.name: p for p in APP.rglob("templates/*.html")}


def _text(path: Path) -> str:
    return _COMMENT.sub("", path.read_text())


def _family(name: str, known: dict[str, Path], seen: set[str] | None = None) -> set[str]:
    """The template and everything it includes, by name."""
    seen = seen if seen is not None else set()
    if name in seen or name not in known:
        return seen
    seen.add(name)
    for included in _INCLUDE.findall(_text(known[name])):
        _family(included, known, seen)
    return seen


def _detail_bodies(text: str) -> list[str]:
    """The call bodies of `ui.row_detail`, nested calls included."""
    bodies = []
    for start in re.finditer(r"{%-?\s*call\s+ui\.row_detail\(", text):
        depth = 0
        for token in re.finditer(r"{%-?\s*(call\b|endcall\b)", text[start.start() :]):
            depth += 1 if token.group(1) == "call" else -1
            if depth == 0:
                bodies.append(text[start.start() : start.start() + token.start()])
                break
    return bodies


def card_on_a_list_tab(family_text: str) -> bool:
    return bool(_CARD.search(family_text) and _LIST.search(family_text))


def edits_in_an_unfolded_row(text: str) -> list[str]:
    found = []
    for body in _detail_bodies(text):
        # The opening call itself names the jump link; what follows is the body.
        inner = body.split("%}", 1)[1] if "%}" in body else body
        found += _EDITS.findall(inner)
    return found


def _pages() -> dict[str, str]:
    """Every page template (it extends a shell) with its family's text."""
    known = _templates()
    pages = {}
    for name, path in known.items():
        if "{% extends" not in path.read_text():
            continue
        pages[name] = "\n".join(_text(known[n]) for n in sorted(_family(name, known)))
    return pages


def test_the_gate_reads_the_tabs_of_the_pilot():
    pages = _pages()
    # Gegevens carries the card; the two list tabs carry a list.
    assert _CARD.search(pages["admin_activiteit.html"])
    assert _LIST.search(pages["admin_activiteit_inschrijvingen.html"])
    assert _LIST.search(pages["admin_activiteit_betalingen.html"])
    # And the unfolded rows it reads: the registrations' and the bookings'.
    bodies = [b for path in _templates().values() for b in _detail_bodies(_text(path))]
    assert len(bodies) >= 2, bodies
    # The one exception still is what it is named for.
    assert all(card_on_a_list_tab(pages[name]) for name in SHOWS_EVERY_MACRO)


def test_no_list_tab_carries_a_summary_card():
    wrong = sorted(
        name
        for name, text in _pages().items()
        if card_on_a_list_tab(text) and name not in SHOWS_EVERY_MACRO
    )
    assert not wrong, f"a summary card beside a list (only Gegevens has one): {wrong}"


def test_no_unfolded_row_edits():
    wrong = {
        path.name: found
        for path in _templates().values()
        if (found := edits_in_an_unfolded_row(_text(path)))
    }
    assert not wrong, f"an unfolded row is read-only (Q42): {wrong}"


CLEAN_TAB = """{% include "_aa_recordkop.html" %}
{% call ui.toolbar("/l", "#l", "f") %}{% endcall %}
{% call ui.data_table(columns) %}<tbody></tbody>{% endcall %}"""
CLEAN_ROW = """{% call ui.row_detail(r.key, 5, open={"label": _("Inschrijving openen"), "href": r.href}) %}
{% call ui.row_part(_("Contact")) %}<div>{{ r.name }}</div>{% endcall %}
{% endcall %}"""


@pytest.mark.parametrize(
    "addition",
    [
        '{{ ui.btn_secondary(_("Bewerken"), href=r.href) }}',
        '<a href="{{ r.href }}?bewerken=1">Bewerken</a>',
        '<button type="button">Opslaan</button>',
        '<form hx-post="/x"><input name="opmerking"></form>',
    ],
)
def test_every_rule_refuses_its_violation(addition):
    assert not edits_in_an_unfolded_row(CLEAN_ROW)
    dirty = CLEAN_ROW.replace("<div>{{ r.name }}</div>", "<div>{{ r.name }}</div>" + addition)
    assert edits_in_an_unfolded_row(dirty), addition


def test_a_summary_card_on_a_list_tab_is_refused():
    assert not card_on_a_list_tab(CLEAN_TAB)
    assert card_on_a_list_tab(CLEAN_TAB + "\n{{ ui.summary_card(summary.state, summary.figures) }}")
    # The card alone, on Gegevens, is what the norm asks.
    assert not card_on_a_list_tab("{{ ui.summary_card(summary.state, summary.figures) }}")


def test_an_edit_outside_the_unfolded_row_is_not_this_gates_business():
    """The gate reads the call body only: a toolbar's button beside the table is
    another rule's."""
    assert not edits_in_an_unfolded_row('{{ ui.btn_primary(_("Bewerken")) }}\n' + CLEAN_ROW)
