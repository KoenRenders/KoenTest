"""CR-11 pilot A, K2 (#1556): the table kit — head and sort, the row as the way in,
one row action, the amount, and the toolbar's sort and column chooser.

The norm is `docs/design-system-end-state.md` §2.1 (block 4, Koen, 2 October
2026). These tests render the macros themselves; Betalingen, the pilot screen,
has its own tests (`payment/tests/test_payments_table.py`), the gate over the
templates is `test_list_page_gate.py`, and the geometry — row height, the
columns that leave, the stacked rows — is measured in a browser
(`tests_e2e/test_betalingen_table.py`).

Proven red (each on this branch, restored after):
- `aria-sort` written on every sortable column → the head test fails;
- a second `<a>` put inside `ui.row_link` → the row-link test fails;
- the delete item rendered in its place in the list → the menu test fails;
- `ui.amount` colouring a negative value → the amount test fails;
- the sort mirror given the name `sort` → the toolbar test fails (sent twice).
"""

from __future__ import annotations

import re

from markupsafe import Markup

from app.ui import templates


def _render(source: str, **context) -> str:
    return templates.env.from_string('{% import "_macros.html" as ui %}' + source).render(**context)


COLUMNS = [
    {
        "key": "naam",
        "label": "Boeking",
        "cell": "name",
        "sort_url": "/l?sort=-naam",
        "sorted": "asc",
    },
    {
        "key": "context",
        "label": "Context",
        "cell": "context",
        "priority": 2,
        "sort_url": "/l?sort=context",
    },
    {"key": "status", "label": "Status", "cell": "status"},
    {
        "key": "bedrag",
        "label": "Bedrag",
        "cell": "amount",
        "num": True,
        "sort_url": "/l?sort=bedrag",
    },
    {"key": "ontvangen", "label": "Ontvangen", "cell": "extra", "num": True, "priority": 1},
    {"key": "acties", "label": "Acties", "cell": "actions"},
]
TABLE = '{% call ui.data_table(columns, modes=modes, hx_target="#l", caption="Lijst") %}<tbody></tbody>{% endcall %}'


def _heads(html: str) -> list[str]:
    return re.findall(r"<th scope=\"col\".*?</th>", html, re.S)


def test_the_head_sorts_with_links_and_marks_the_one_that_sorts():
    html = _render(TABLE, columns=COLUMNS, modes={1: "show"})
    heads = _heads(html)
    assert len(heads) == 6
    # A sortable column is a link; one that does not sort is text.
    assert ["<a " in h for h in heads] == [True, True, False, True, False, False]
    # `aria-sort` on the column that sorts, and on no other.
    assert ["aria-sort=" in h for h in heads] == [True, False, False, False, False, False]
    assert 'aria-sort="ascending"' in heads[0]
    # One arrow in its direction on the active column, the double arrow on the others.
    arrow_up_down = "m21 16-4 4-4-4"
    assert arrow_up_down not in heads[0] and arrow_up_down in heads[1] and arrow_up_down in heads[3]
    # Numbers right-aligned; the fragment link is marked so the URL keeps the sort.
    assert "text-right" in heads[3] and "text-right" not in heads[0]
    assert 'hx-get="/l?sort=bedrag"' in heads[3] and "X-Raak-Filter" in heads[3]
    # The link carries its own state: it must not inherit the list holder's include.
    assert 'hx-include="unset"' in heads[3]
    # The actions column has a name for a screen reader only.
    assert 'class="sr-only">Acties<' in heads[5]
    # Optional columns carry their priority; the table says what the chooser chose.
    assert 'data-p="2"' in heads[1] and 'data-p="1"' in heads[4]
    assert 'data-p1="show"' in html and 'data-p2="auto"' in html
    assert "<caption" in html and "data-table-frame" in html


def test_a_descending_column_points_down():
    columns = [dict(COLUMNS[0], sorted="desc")]
    head = _heads(_render(TABLE, columns=columns, modes={}))[0]
    assert 'aria-sort="descending"' in head
    assert "M12 5v14" in head, "the arrow does not point down"


def test_the_row_link_is_one_anchor_with_its_reference_under_it():
    html = _render('{{ ui.row_link("An Voorbeeld", "/r/7", sub="+++000/0000/00097+++") }}')
    assert html.count("<a ") == 1, "a second anchor: links may not nest in a row"
    assert re.search(r'<a href="/r/7" data-row-link[^>]*>An Voorbeeld</a>', html)
    assert "+++000/0000/00097+++" in html and "<small" in html


ACTION = {"label": "Bevestig", "attrs": 'hx-post="/x"', "confirm": "Zeker?"}
ITEMS = [
    {"kind": "delete", "label": "Verwijderen", "attrs": 'hx-post="/d"', "confirm": "Weg?"},
    {"label": "Terugbetaling", "href": "/r/7#terugbetaling"},
    {"label": "Inschrijving openen", "href": "/i/3"},
]


def _cell(action=None, items=()) -> str:
    return _render(
        '{{ ui.row_actions_cell(action, items, label="An Voorbeeld") }}',
        action=action,
        items=list(items),
    )


def test_a_row_shows_one_action_and_the_menu_puts_delete_last():
    html = _cell(ACTION, ITEMS)
    assert html.count("data-row-action") == 1
    assert 'data-confirm="Zeker?"' in html and 'hx-post="/x"' in html
    menu = html[html.index("data-row-menu") :]
    order = [
        menu.index("Terugbetaling"),
        menu.index("Inschrijving openen"),
        menu.index("Verwijderen"),
    ]
    assert order == sorted(order), "delete is not the last item"
    assert menu.index("data-menu-divider") < menu.index("Verwijderen")
    delete = menu[menu.index("data-menu-divider") :]
    assert "text-red-700" in delete and 'data-confirm="Weg?"' in delete
    assert "text-red-700" not in menu[: menu.index("data-menu-divider")], "red is for delete only"
    assert "Bewerken" not in html
    assert 'aria-label="Meer acties: An Voorbeeld"' in html, "the ⋯ does not say whose it is"


def test_a_row_without_action_or_items_keeps_the_cell_quiet():
    assert "data-row-action" not in _cell(None, ITEMS[1:])
    assert "data-row-menu-trigger" in _cell(None, ITEMS[1:])
    bare = _cell(ACTION, [])
    assert "data-row-action" in bare and "data-row-menu-trigger" not in bare
    # An item without a `kind` is an ordinary one (StrictUndefined once refused it).
    assert "data-menu-divider" not in _cell(None, ITEMS[1:])


def test_an_amount_is_never_coloured_and_carries_its_sign_before_the_euro():
    html = _render(
        "{{ ui.amount(a) }}|{{ ui.amount(b) }}|{{ ui.amount(c, warning=True) }}", a=45, b=-15, c=-15
    )
    plain, negative, balance = html.split("|")
    assert "€ 45,00" in plain and "−" not in plain
    assert "− € 15,00" in negative
    for cell in (plain, negative):
        assert not re.search(r"text-(red|orange|teal|green|brand)", cell), cell
    assert "text-brand-warning" in balance and "− € 15,00" in balance
    assert "tabular-nums" in plain


def test_an_amount_carries_its_balance_only_when_it_says_something():
    """#1582: a stacked row has no Saldo column, so the amount carries the
    balance under it — when it differs from the amount and is not zero.

    Proven red (on this branch, restored after): the condition reduced to
    "not zero" → the fully-open case fails; the `data-stacked-only` mark left
    off → the mark assertion fails (a wide list would show the balance twice)."""
    cells = _render(
        "{{ ui.amount(40, balance=20) }}|{{ ui.amount(40, balance=40) }}|"
        "{{ ui.amount(40, balance=0) }}|{{ ui.amount(40) }}|{{ ui.amount(40, balance=-5) }}|"
        "{{ ui.amount(-15, balance=-15) }}"
    ).split("|")
    partly, open_, settled, plain, overpaid, refund_due = cells
    # Partly paid: "nog € 20,00" under the amount, in the warning tone — and
    # only in a stacked row.
    assert "€ 40,00" in partly and "nog € 20,00" in partly
    extra = re.search(r"<span data-stacked-only data-stacked-balance[^>]*>", partly).group(0)
    assert "text-brand-warning" in extra and "block" in extra
    # The amount itself stays uncoloured (Q36).
    first = partly.split("<span data-stacked-only")[0]
    assert "text-brand-warning" not in first
    # Fully open, settled, or no balance given: nothing extra.
    for cell in (open_, settled, plain, refund_due):
        assert "data-stacked-balance" not in cell, cell
    # Too much received: what goes back, as a positive amount with its word.
    assert "terug € 5,00" in overpaid and "−" not in overpaid.split("data-stacked-balance")[1]


TOOLBAR = """{% call ui.toolbar("/lijst", "#lijst", "t", page=1, per_page=50, total=3,
     sort="-naam", sort_options=options, columns=columns) %}{% endcall %}"""


def test_the_toolbar_carries_the_sort_once_and_the_column_chooser():
    html = _render(
        TOOLBAR,
        options=[("", "Recentste eerst"), ("naam", "Naam (A–Z)"), ("-naam", "Naam (Z–A)")],
        columns=[
            {"key": "ontvangen", "label": "Ontvangen", "mode": "hide"},
            {"key": "context", "label": "Context", "mode": "auto"},
        ],
    )
    # One field named `sort`; the phone's "Sorteren" is a mirror without a name.
    assert html.count('name="sort"') == 1
    assert re.search(
        r'<input type="hidden" id="t-sort" name="sort" value="-naam" data-sort-field>', html
    )
    mirror = html[html.index("data-sort-mirror") - 200 : html.index("data-sort-mirror")]
    assert 'name=""' in mirror
    assert re.search(r'<option value="-naam" selected>Naam \(Z–A\)</option>', html)
    # The chooser: per optional column Automatisch / Tonen / Verbergen, a field of the form.
    chooser = html[html.index("data-columns-chooser") :]
    assert "Kolommen" in chooser
    assert re.search(
        r'name="kol_ontvangen".*?<option value="hide" selected>Verbergen</option>', chooser, re.S
    )
    assert re.search(
        r'name="kol_context".*?<option value="auto" selected>Automatisch</option>', chooser, re.S
    )
    assert chooser.count("<option") >= 6


def test_the_out_of_band_part_carries_the_sort():
    html = _render('{{ ui.toolbar_oob("t", page=1, per_page=50, total=3, sort="bedrag") }}')
    assert re.search(
        r'<input type="hidden" id="t-sort" name="sort" value="bedrag" data-sort-field hx-swap-oob="true">',
        html,
    )
    assert "t-sort" not in _render('{{ ui.toolbar_oob("t", page=1, per_page=50, total=3) }}')


def test_markup_in_a_label_is_escaped():
    html = _render('{{ ui.row_link(name, "/r/7") }}', name="<b>An</b>")
    assert "<b>" not in html and Markup.escape("<b>An</b>") in html
