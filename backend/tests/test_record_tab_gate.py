"""CR-11 pilot A, K6 (#1560): what a record's tab may not do.

Block 8 (Koen, 4 October 2026; `docs/design-system-end-state.md` §2.2, §3.10):

1. **a summary card on a list tab** — the card stands on Gegevens only; a tab
   that holds a list (a table or a toolbar) starts directly under the tabs at
   the full width. A page whose template family renders both `ui.summary_card`
   and a list is red.
2. **a disclosure inside a kit table** (#1636, Koen, 5 October 2026; CR-11
   Q75; P8 in `docs/design-system.md`) — a row is the way in to its record, on
   a main list and on a record's tab alike; it unfolds nowhere. K6 let a row
   unfold read-only, and the same data stood three times: the row, the
   unfolded row, the record. So no template may call `ui.row_toggle`,
   `ui.row_detail` or `ui.row_part` — the kit no longer has them — nor write
   their hooks by hand, nor a `<details>` inside a `ui.data_table`. A group
   row that collapses its rows (`ui.table_group`) is not a disclosure of a
   row: the rows stay rows.

The gate reads every page template and what it includes. It counts what it
read (`test_the_gate_reads_the_tabs_of_the_pilot`): a gate that finds nothing
is green for ever.

Proven red, additively — each rule on a throwaway template text that adds one
violation to a clean one (`test_every_rule_refuses_its_violation`); and on the
real tree: against master `92866b83` the disclosure rule names
`_inschrijvingen_groepen.html`, `_betalingen_lijst.html`, `design_system.html`
and the kit itself.
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

#: What an unfolding row is made of: the three kit macros K6 had, their hooks
#: written by hand, and the Alpine state that opened one row.
_DISCLOSURE = re.compile(
    r"ui\.row_toggle\(|ui\.row_detail\(|ui\.row_part\(|macro row_toggle\(|macro row_detail\("
    r"|macro row_part\(|data-row-toggle|data-row-detail|data-row-part|openRow\s*[:=]"
)
_TABLE = re.compile(r"{%-?\s*call\s+ui\.data_table\(")


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


def _table_bodies(text: str) -> list[str]:
    """The call bodies of `ui.data_table`, nested calls included."""
    bodies = []
    for start in _TABLE.finditer(text):
        depth = 0
        for token in re.finditer(r"{%-?\s*(call\b|endcall\b)", text[start.start() :]):
            depth += 1 if token.group(1) == "call" else -1
            if depth == 0:
                bodies.append(text[start.start() : start.start() + token.start()])
                break
    return bodies


def card_on_a_list_tab(family_text: str) -> bool:
    return bool(_CARD.search(family_text) and _LIST.search(family_text))


def disclosures(text: str) -> list[str]:
    """Every trace of a row that unfolds, and a `<details>` inside a kit table."""
    found = _DISCLOSURE.findall(text)
    for body in _table_bodies(text):
        found += re.findall(r"<details\b", body)
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
    # And the kit tables it reads: the registrations', the bookings', the demo.
    tables = [b for path in _templates().values() for b in _table_bodies(_text(path))]
    assert len(tables) >= 3, len(tables)
    assert len(_templates()) > 100, "hardly a template was read"
    # The one exception still is what it is named for.
    assert all(card_on_a_list_tab(pages[name]) for name in SHOWS_EVERY_MACRO)


def test_no_list_tab_carries_a_summary_card():
    wrong = sorted(
        name
        for name, text in _pages().items()
        if card_on_a_list_tab(text) and name not in SHOWS_EVERY_MACRO
    )
    assert not wrong, f"a summary card beside a list (only Gegevens has one): {wrong}"


def test_no_kit_table_has_an_inline_disclosure():
    wrong = {
        path.name: sorted(set(found))
        for path in _templates().values()
        if (found := disclosures(_text(path)))
    }
    assert not wrong, f"a row unfolds nowhere — it is the way in to its record (Q75): {wrong}"


CLEAN_TAB = """{% include "_aa_recordkop.html" %}
{% call ui.toolbar("/l", "#l", "f") %}{% endcall %}
{% call ui.data_table(columns) %}<tbody></tbody>{% endcall %}"""
CLEAN_TABLE = """{% call ui.data_table(columns) %}
<tr data-row data-row-key="{{ r.key }}"><td data-cell="name">{{ ui.row_link(r.name, r.href) }}</td></tr>
{% endcall %}"""


@pytest.mark.parametrize(
    "addition",
    [
        "{{ ui.row_toggle(r.name, r.key) }}",
        "{% call ui.row_detail(r.key, 5) %}{% call ui.row_part(_('Contact')) %}x{% endcall %}{% endcall %}",
        '<button data-row-toggle="{{ r.key }}">open</button>',
        "<tr data-row-detail x-show=\"openRow === '{{ r.key }}'\"><td>meer</td></tr>",
        "<tr x-data=\"{ openRow: '' }\"><td>meer</td></tr>",
        "<tr><td><details><summary>meer</summary>alles nog eens</details></td></tr>",
    ],
)
def test_every_rule_refuses_its_violation(addition):
    assert not disclosures(CLEAN_TABLE)
    dirty = CLEAN_TABLE.replace("</tr>", "</tr>" + addition, 1)
    assert disclosures(dirty), addition


def test_a_group_that_collapses_and_a_details_outside_a_table_are_not_a_disclosure():
    """The rule is about a ROW of a kit table. A group row hides and shows its
    rows (`ui.table_group`), and a `<details>` elsewhere on a page — the
    legend of the page editor — is another matter."""
    group = CLEAN_TABLE.replace(
        "<tr data-row", "{% call ui.table_group(g.name, g.count, 5) %}<tr data-row"
    ).replace("</tr>", "</tr>{% endcall %}", 1)
    assert not disclosures(group)
    assert not disclosures(
        "<details><summary>Beschikbare placeholders</summary></details>\n" + CLEAN_TABLE
    )


def test_a_summary_card_on_a_list_tab_is_refused():
    assert not card_on_a_list_tab(CLEAN_TAB)
    assert card_on_a_list_tab(CLEAN_TAB + "\n{{ ui.summary_card(summary.state, summary.figures) }}")
    # The card alone, on Gegevens, is what the norm asks.
    assert not card_on_a_list_tab("{{ ui.summary_card(summary.state, summary.figures) }}")
