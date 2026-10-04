"""CR-11 pilot A, K1 (#1555): what a template on the `list_page` layout may not do.

`list_page.html` gives a list two rows of chrome — the title row with the key
figures, and the toolbar — and the kit owns both (`docs/design-system-end-state.md`
§2.1, §3.13). This gate reads the templates that extend the layout, and the
partials they include, and refuses what the blocks 2 and 3 decided against
(Koen, 2 October 2026):

1. **a tab bar** — a list filters with the toolbar's status filter; tabs are a
   record's way to its linked objects and nothing else (CR-11 B7 test 5);
2. **a select loose in the row** — in a template that carries the toolbar, a
   select outside the toolbar's call body, which is the Filters panel
   (B7 test 5, decision 03 point 4);
3. **a checkbox group in the toolbar** — the multi-select is the only
   multi-choice there (B7 test 23);
4. **the old chrome** — `ui.filter_bar`, `ui.page_header`, `ui.list_meta`'s
   page-size select (`ui.per_page_select`) and `ui.chips` beside the toolbar;
5. **a pager that keeps its count or its page to itself** — `ui.pager` without
   `count=False` (the count stands in the toolbar) or without `push=True` (the
   page must land in the URL, B7 test 21);
6. **anything beside the toolbar** — a per-screen `AI ·` button
   (`raakje.overlay`), except the screens named in `BESIDE_THE_TOOLBAR`.

Since K2 (#1556, block 4) the list fragment — the table itself — has rules too:

7. **"Bewerken" in a row** — the row is the way in (B7 test 6);
8. **a row control of its own** — a `btn_*`, a `link_action`, the old
   `row_actions` or a raw `<button>` in a row: a row shows at most one action
   and `⋯`, and `ui.row_actions_cell` draws both;
9. **a coloured Bedrag** — a `data-amount` cell with a colour class or a
   `warning=` (Q36: Bedrag never coloured, also when negative);
10. **a Saldo without its warning** — a `data-balance` cell that does not pass
    `warning=` (Q36: a balance that is not zero takes the warning tone);
11. **a key figure drawn by hand** — `data-figure` markup in a template: a figure
    comes from `ui.figures`, which makes it plain text and never a link or a
    button (B7 test 5).

`BESIDE_THE_TOOLBAR` is a list that may only shrink. Its one entry is the
"AI · Betalingen" button: it stays outside the toolbar, at the right of its row,
until K8 (#1562) lets the shell's Assistent panel read the screen's selection
(the master CLI, 4 October 2026). An entry whose template no longer carries the
call must leave the list.

The list fragment that a screen swaps (`_betalingen_lijst.html`) holds the
table; rule 2 does not read it, rules 7–10 read only it.

Proven red, additively — each rule on a throwaway template text that adds one
violation to a clean one (`test_every_rule_refuses_its_violation`); and the
gate counts what it read (`test_the_gate_reads_the_pilot_screen`), because a
gate that finds no template is green for ever.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "app"

#: Screens that still carry something beside their toolbar, and until when.
BESIDE_THE_TOOLBAR = {
    "_betalingen_scherm.html": "raakje.overlay — the AI · Betalingen button, until K8 (#1562)",
}

#: Partials that are the swapped list itself, not the chrome above it.
LIST_FRAGMENTS = {"_betalingen_lijst.html"}


def _templates() -> dict[str, Path]:
    return {p.name: p for p in APP.rglob("templates/**/*.html")}


def _family(name: str, known: dict[str, Path], seen: set[str] | None = None) -> set[str]:
    """A template and every partial it includes, by file name."""
    seen = seen if seen is not None else set()
    if name in seen or name not in known:
        return seen
    seen.add(name)
    for included in re.findall(r'{%-?\s*include\s+"([^"]+)"', known[name].read_text("utf-8")):
        _family(included.rsplit("/", 1)[-1], known, seen)
    return seen


def list_page_templates() -> dict[str, str]:
    """Every template on the layout, with its partials: file name → text."""
    known = _templates()
    on_layout = [
        name
        for name, path in known.items()
        if re.search(r'{%-?\s*extends\s+"list_page\.html"', path.read_text("utf-8"))
    ]
    names: set[str] = set()
    for name in on_layout:
        _family(name, known, names)
    return {name: known[name].read_text("utf-8") for name in sorted(names)}


def _without_comments(text: str) -> str:
    return re.sub(r"{#.*?#}", "", text, flags=re.S)


def _outside_toolbar(text: str) -> str:
    """The template without the call bodies of `ui.toolbar` (the Filters panel)."""
    return re.sub(r"{%-?\s*call\s+ui\.toolbar\(.*?{%-?\s*endcall\s*-?%}", "", text, flags=re.S)


def _toolbar_bodies(text: str) -> str:
    return "\n".join(
        re.findall(r"{%-?\s*call\s+ui\.toolbar\(.*?%}(.*?){%-?\s*endcall\s*-?%}", text, flags=re.S)
    )


def violations(name: str, text: str) -> list[str]:
    """What this template does that a list page may not."""
    text = _without_comments(text)
    found = []
    if re.search(r"ui\.tabs\(|role=\"tablist\"", text):
        found.append(f"{name}: a tab bar on a list page — the status filter filters (rule 1)")
    if name not in LIST_FRAGMENTS and "ui.toolbar(" in text:
        loose = _outside_toolbar(text)
        if re.search(r"ui\.select_control\(|ui\.grouped_filter\(|<select\b", loose):
            found.append(f"{name}: a select outside the Filters panel (rule 2)")
    if "ui.checkbox_group(" in _toolbar_bodies(text):
        found.append(f"{name}: a checkbox group in the toolbar — use ui.multiselect (rule 3)")
    for old in ("ui.filter_bar(", "ui.page_header(", "ui.per_page_select(", "ui.chips("):
        if old in text:
            found.append(
                f"{name}: {old}…) on a list page — the layout and ui.toolbar own it (rule 4)"
            )
    for call in re.findall(r"ui\.pager\((.*?)\)\s*}}", text, flags=re.S):
        if "count=False" not in call or "push=True" not in call:
            found.append(f"{name}: ui.pager without count=False and push=True (rule 5)")
    if "raakje.overlay(" in text and name not in BESIDE_THE_TOOLBAR:
        found.append(f"{name}: a per-screen AI button beside the toolbar (rule 6)")
    if name in LIST_FRAGMENTS:
        if "ui.edit_toggle(" in text or re.search(r"_\(\s*[\"']Bewerken[\"']\s*\)", text):
            found.append(f'{name}: "Bewerken" in a row — the row is the way in (rule 7)')
        if re.search(
            r"ui\.btn_\w+\(|ui\.button\(|ui\.link_action\(|ui\.row_actions\(|<button\b", text
        ):
            found.append(f"{name}: a row control outside ui.row_actions_cell (rule 8)")
        for line in text.splitlines():
            if "data-amount" in line and (
                "warning=" in line or re.search(r"text-(red|orange|teal|green|brand)", line)
            ):
                found.append(f"{name}: a coloured Bedrag (rule 9)")
            if "data-balance" in line and "ui.amount(" in line and "warning=" not in line:
                found.append(f"{name}: a Saldo without its warning (rule 10)")
    if "data-figure" in text:
        found.append(f"{name}: a key figure drawn by hand — use ui.figures (rule 11)")
    return found


def test_the_gate_reads_the_pilot_screen():
    """A gate that looks nowhere is green for ever: Betalingen and its partials
    must be among what it reads, with the toolbar and the pager in them."""
    family = list_page_templates()
    assert {"betalingen.html", "_betalingen_scherm.html", "_betalingen_lijst.html"} <= set(family)
    assert "ui.toolbar(" in family["_betalingen_scherm.html"]
    assert "ui.pager(" in family["_betalingen_lijst.html"]
    assert "ui.figures(" in family["betalingen.html"]


def test_no_list_page_breaks_the_layouts_rules():
    found = [v for name, text in list_page_templates().items() for v in violations(name, text)]
    assert not found, "\n".join(found)


def test_the_exceptions_still_exist():
    """An entry may only leave: once its template drops the call, it is dead
    weight that would hide the next one."""
    family = list_page_templates()
    for name in BESIDE_THE_TOOLBAR:
        assert name in family and "raakje.overlay(" in _without_comments(family[name]), (
            f"{name} no longer carries what BESIDE_THE_TOOLBAR excuses — remove the entry"
        )
    assert len(BESIDE_THE_TOOLBAR) <= 1, "this list only shrinks"


CLEAN = """{% call ui.toolbar("/l", "#l", "t") %}{{ ui.grouped_filter("context") }}{% endcall %}
<div id="l">{{ ui.pager(page, per_page=per_page, total=n, hx_get=u, count=False, push=True) }}</div>"""


@pytest.mark.parametrize(
    "addition, rule",
    [
        ("{{ ui.tabs(items) }}", "rule 1"),
        ('{{ ui.grouped_filter("jaar") }}', "rule 2"),
        ('{% call ui.select_control("status") %}{% endcall %}', "rule 2"),
        ('<select name="status"></select>', "rule 2"),
        ('{% call ui.filter_bar("/l", "#l") %}{% endcall %}', "rule 4"),
        ('{{ ui.page_header("Titel") }}', "rule 4"),
        ("{{ ui.pager(page, per_page=per_page, total=n, hx_get=u) }}", "rule 5"),
        ("{{ ui.pager(page, per_page=per_page, total=n, hx_get=u, count=False) }}", "rule 5"),
        ('{{ raakje.overlay("AI · Leden", "/x", "Dag") }}', "rule 6"),
    ],
)
def test_every_rule_refuses_its_violation(addition, rule):
    assert violations("_throwaway.html", CLEAN) == []
    found = violations("_throwaway.html", CLEAN + "\n" + addition)
    assert len(found) == 1 and rule in found[0], found


def test_a_checkbox_group_in_the_toolbar_is_refused():
    inside = CLEAN.replace(
        '{{ ui.grouped_filter("context") }}', '{{ ui.checkbox_group("status", values) }}'
    )
    found = violations("_throwaway.html", inside)
    assert len(found) == 1 and "rule 3" in found[0], found


ROW = """<tr data-row><td data-cell="name">{{ ui.row_link(k.name, k.href) }}</td>
<td data-cell="amount" data-amount>{{ ui.amount(k.bedrag) }}</td>
<td data-cell="extra" data-balance>{{ ui.amount(k.saldo, warning=k.saldo != 0) }}</td>
<td data-cell="actions">{{ ui.row_actions_cell(k.action, k.menu) }}</td></tr>"""


@pytest.mark.parametrize(
    "addition, rule",
    [
        ('{{ ui.edit_toggle("open") }}', "rule 7"),
        ('<a href="/x">{{ _("Bewerken") }}</a>', "rule 7"),
        ('{{ ui.link_action(_("Inschrijving"), href="/i") }}', "rule 8"),
        ('{{ ui.btn_secondary(_("Bevestig"), size="sm") }}', "rule 8"),
        ("{{ ui.row_actions([a, b], max_visible=2) }}", "rule 8"),
        ('<td data-amount class="text-orange-700">{{ ui.amount(k.bedrag) }}</td>', "rule 9"),
        ("<td data-amount>{{ ui.amount(k.bedrag, warning=True) }}</td>", "rule 9"),
        ("<td data-balance>{{ ui.amount(k.saldo) }}</td>", "rule 10"),
    ],
)
def test_every_table_rule_refuses_its_violation(addition, rule):
    """The table's rules read the list fragment only; each proven by adding one
    violation to a clean row."""
    fragment = next(iter(LIST_FRAGMENTS))
    assert violations(fragment, ROW) == []
    found = violations(fragment, ROW + "\n" + addition)
    assert len(found) == 1 and rule in found[0], found


def test_a_key_figure_drawn_by_hand_is_refused():
    by_hand = '<a href="/x"><dd data-figure>€ 9,00</dd></a>'
    found = violations("_throwaway.html", CLEAN + "\n" + by_hand)
    assert len(found) == 1 and "rule 11" in found[0], found


def test_the_gate_reads_the_table_of_the_pilot_screen():
    """Rules 7–10 must find something to read: the fragment carries the row
    link, an amount cell, a balance cell with its warning and the actions cell."""
    fragment = list_page_templates()["_betalingen_lijst.html"]
    for piece in (
        "ui.row_link(",
        "data-amount",
        "data-balance",
        "warning=",
        "ui.row_actions_cell(",
    ):
        assert piece in fragment, piece


def test_a_comment_that_names_a_macro_is_not_a_violation():
    assert violations("_throwaway.html", CLEAN + "\n{# was: ui.tabs(items) #}") == []
