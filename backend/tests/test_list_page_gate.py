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

`BESIDE_THE_TOOLBAR` is a list that may only shrink. Its one entry is the
"AI · Betalingen" button: it stays outside the toolbar, at the right of its row,
until K8 (#1562) lets the shell's Assistent panel read the screen's selection
(the master CLI, 4 October 2026). An entry whose template no longer carries the
call must leave the list.

The list fragment that a screen swaps (`_betalingen_lijst.html`) holds the
table and its row editors; rule 2 does not read it — a status select in a row's
edit form is no filter. K2 (#1556) owns the table.

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


def test_a_comment_that_names_a_macro_is_not_a_violation():
    assert violations("_throwaway.html", CLEAN + "\n{# was: ui.tabs(items) #}") == []
