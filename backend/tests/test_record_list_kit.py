"""CR-11 pilot A, K6 (#1560): the kit of a record's summary and its related
lists — the summary card, the group row, the row that unfolds.

The norm is `docs/design-system-end-state.md` §2.2 and §3.10 (block 8, Koen,
4 October 2026). These tests render the macros themselves; the activity's tabs
have their own tests (`tests/integration/test_activity_tabs.py`), the gate over
the templates is `test_record_tab_gate.py`, and what only a browser shows — one
open row per list, the card's size, the copy button — is in
`tests_e2e/test_activity_tabs.py`.

Proven red (each on this branch, restored after):
- the warning tone written on every figure → the summary test fails;
- the copy button left out of the card's action → the action test fails;
- `ui.row_toggle` drawn as a link → the toggle test fails;
- `x-show` taken off `ui.row_detail` → the detail test fails;
- the group's count without its brackets → the group test fails.
"""

from __future__ import annotations

import re

from app.ui import templates


def _render(source: str, **context) -> str:
    return templates.env.from_string('{% import "_macros.html" as ui %}' + source).render(**context)


CARD = "{{ ui.summary_card(state, figures, action) }}"
FIGURES = [
    {"label": "Inschrijvingen", "value": "23"},
    {"label": "Deelnemers", "value": "41"},
    {"label": "Openstaand", "value": "€ 312,56", "warning": True},
]


def test_the_summary_card_says_the_state_first_then_the_figures():
    html = _render(
        CARD, state={"label": "Gepubliceerd", "tone": "green"}, figures=FIGURES, action=None
    )
    assert html.index("data-summary-state") < html.index("data-summary-figures")
    assert ">Gepubliceerd<" in html
    figures = re.findall(r"<div data-summary-figure>.*?</div>", html, re.S)
    assert len(figures) == 3
    # Only the open balance asks for attention; a count never does.
    assert ["text-brand-warning" in f for f in figures] == [False, False, True]
    assert "tabular-nums" in figures[2] and "€ 312,56" in figures[2]
    # No action, no action row — and no empty copy button.
    assert "data-summary-action" not in html and "data-copy" not in html


def test_the_summary_card_shows_at_most_three_figures():
    four = FIGURES + [{"label": "Vierde", "value": "4"}]
    html = _render(CARD, state=None, figures=four, action=None)
    assert html.count("<div data-summary-figure>") == 3 and "Vierde" not in html
    assert "data-summary-state" not in html


def test_the_summary_cards_action_is_the_link_with_its_copy_button():
    action = {
        "href": "https://voorbeeld.test/activiteiten/wandeling",
        "text": "voorbeeld.test/activiteiten/wandeling",
        "label": "Kopieer de publieke link",
    }
    html = _render(CARD, state=None, figures=[], action=action)
    block = html[html.index("data-summary-action") :]
    assert re.search(
        r'data-summary-link[^>]* href="https://voorbeeld.test/activiteiten/wandeling"', block
    )
    assert ">voorbeeld.test/activiteiten/wandeling<" in block
    # The kit's copy button (Q49): it copies in place and shows its check mark;
    # the card opens no screen and writes no toast.
    assert 'data-copy="https://voorbeeld.test/activiteiten/wandeling"' in block
    assert 'aria-label="Kopieer de publieke link"' in block and "raakKopieer" in block
    assert "toast" not in block and "modal" not in block


GROUP = """{% call ui.data_table(columns, open_row=open_row) %}
{% call ui.table_group("Wandeling", 18, 5, items=items, link=link) %}
<tr data-row><td>{{ ui.row_toggle("Emma Voorbeeld", "7") }}</td></tr>
{% call ui.row_detail("7", 5, open={"label": "Inschrijving openen", "href": "/admin/inschrijvingen/7"}) %}
{% call ui.row_part("Contact") %}<div>Emma Voorbeeld</div>{% endcall %}
{% endcall %}
{% endcall %}
{% endcall %}"""
COLUMNS = [
    {"key": "naam", "label": "Naam", "cell": "name", "sort_url": "/t?sort=-naam", "sorted": "asc"},
    {"key": "status", "label": "Status", "cell": "status"},
]
ITEMS = [
    {"label": "Exporteren", "href": "/export", "attrs": 'hx-boost="false"'},
    {"label": "Antwoorden", "href": "/antwoorden"},
]


def _group(**extra) -> str:
    context = {"columns": COLUMNS, "items": ITEMS, "link": None, "open_row": ""} | extra
    return _render(GROUP, **context)


def test_a_group_is_a_row_of_the_table_with_its_count_and_its_menu():
    html = _group()
    # One table, the group a tbody of it — never a card per group.
    assert html.count("<table") == 1 and html.count("<tbody data-group") == 1
    row = re.search(r"<tr data-group-row.*?</tr>", html, re.S).group(0)
    assert "Wandeling" in row and re.search(r"data-group-count[^>]*>\(18\)<", row)
    assert 'colspan="4"' in row
    # The toggle is a button that says whether the group is shown.
    assert "data-group-toggle" in row and ":aria-expanded" in row
    # Exporteren and Antwoorden under the group's ⋯ (Q41), not as buttons.
    menu = row[row.index("data-row-menu") :]
    assert menu.index("Exporteren") < menu.index("Antwoorden")
    assert 'href="/export"' in menu and 'hx-boost="false"' in menu
    assert "data-row-action" not in row


def test_a_group_row_carries_a_jump_link_when_it_names_a_record():
    html = _group(link={"label": "Open activiteit", "href": "/admin/activiteiten/3"})
    row = re.search(r"<tr data-group-row.*?</tr>", html, re.S).group(0)
    assert 'href="/admin/activiteiten/3" data-reference' in row
    assert "data-reference" not in re.search(r"<tr data-group-row.*?</tr>", _group(), re.S).group(0)


def test_a_row_that_unfolds_is_a_button_and_never_a_link():
    html = _group()
    cell = re.search(r"<tr data-row>.*?</tr>", html, re.S).group(0)
    assert '<button type="button" data-row-toggle="7"' in cell and "<a " not in cell
    assert 'aria-controls="row-detail-7"' in cell and ":aria-expanded" in cell
    assert "data-row-link" not in html


def test_the_unfolded_row_is_hidden_until_it_is_the_open_one():
    html = _group()
    detail = re.search(r"<tr data-row-detail.*?</tr>", html, re.S).group(0)
    assert 'id="row-detail-7"' in detail and "x-show=\"openRow === '7'\"" in detail
    assert "x-cloak" in detail and 'colspan="5"' in detail
    # The parts, and the jump link to the row's own page under them.
    assert "data-row-part" in detail and ">Contact<" in detail
    assert 'href="/admin/inschrijvingen/7" data-reference' in detail
    assert detail.index("data-row-part") < detail.index("Inschrijving openen")


def test_the_table_holds_one_open_row_and_opens_it_from_the_url():
    # One state for the whole list: a second toggle replaces the first.
    assert "x-data=\"{ openRow: '' }\"" in _group()
    assert "x-data=\"{ openRow: '7' }\"" in _group(open_row="7")
    assert _group().count("openRow:") == 1
    # Only a list that opens on a row lands on it (in view, with the focus).
    assert 'data-open-row="7"' in _group(open_row="7") and "raakOpenRij" in _group(open_row="7")
    assert "data-open-row" not in _group() and "raakOpenRij" not in _group()


def test_a_sort_link_without_a_list_fragment_is_a_plain_link():
    """The household's tab has no list fragment of its own: its sort link is the
    page. With a target the link asks the fragment (K2)."""
    plain = _group()
    assert 'href="/t?sort=-naam"' in plain and "hx-get" not in plain
    swapped = _render(
        '{% call ui.data_table(columns, hx_target="#l") %}<tbody></tbody>{% endcall %}',
        columns=COLUMNS,
    )
    assert 'hx-get="/t?sort=-naam"' in swapped and 'hx-target="#l"' in swapped
