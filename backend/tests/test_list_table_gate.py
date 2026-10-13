"""Refuses a new back-office list of records drawn by hand instead of `ui.data_table` · ratchet · since #1911.

#1911: a list of records in the back office comes from the kit's table.

Koen, 12 October 2026, after two list screens of a builder turned out to be
hand-written cards while the same builder's third used `ui.data_table`: "Hebben
we geen gate die bewaakt dat op lijst-schermen enkel nog via de macro mag gewerkt
worden?" Nothing mechanical said it, so no review brought it back.

The lists move onto the macro one at a time (`docs/design-system-end-state.md`
§2.1), so "every list on the macro" would be red today. This is a ratchet in the
shape of #780's: `HAND_DRAWN_LISTS` holds the templates that draw a list by hand
on 12 October 2026, it may only shrink, and nothing outside it may draw one.

**How the gate knows a list of records** — two signals, both read from the
template's own text, neither a guess about its looks:

1. **a screen on the list layout without the table**: a template that extends
   `list_page.html` and whose family (itself and what it includes) never calls
   `ui.data_table(`. The layout is the kit's page for a list and nothing else;
2. **a loop of ways in**: a `{% for x in … %}` whose body holds a link to a
   back-office address that begins with the item's own identity —
   `href="/admin/<path>/{{ x.… }}"`, or the same written as `"/admin/<path>/" ~ x.…`
   — outside the body of a `ui.data_table` call. "The row is the way in" is what
   makes a row a record's row (§2.1); a card per record with such a link is the
   same list in another coat.

What the signals do NOT call a list, on purpose: tiles whose address comes from
the view-model (`href="{{ tile.href }}"` — the dashboard's key figures, the menu);
a record's own parts, whose address begins with the RECORD's identity and not the
item's (`/admin/vergaderingen/{{ meeting.id }}/bestanden/{{ file.id }}`); a group
of a record's form (no link at all).

What the gate cannot see, said so nobody leans on it for more: a table written by
hand whose rows are no way in (nine templates today — the e-mail log, the users,
the subscribers, the AI costs, a report's result), and a hand-drawn list whose
rows take their address from the view-model while the screen is not on the list
layout. The rows of a `ui.data_table` are written in the template that calls it;
rows in a partial included from the call's body would read as a loop of their own.

Proven red, additively (`test_the_gate_refuses_a_list_drawn_by_hand`): the
markup of the two screens that started this, as they stood on the builder's
branch, laid into a throwaway template — each red on both signals; and proven NOT
red on a block of key-figure tiles, on a record's files and on the same loop
inside the table's call (`test_the_gate_leaves_what_is_no_list_alone`). Proven on
the tree too, 12 October 2026, each an addition that was removed again: the
three templates of those two screens laid into an added folder → both screens
named "on the list layout without ui.data_table" and both loops "draws a list of
records by hand"; a copy of `_aa_kaarten.html` under a new name → the same.

The gate counts what it read and what it recognised: a gate that finds no
template, or no list at all, is green for ever.
"""

from __future__ import annotations

import re

import pytest

from tests.test_list_page_gate import APP, _family, _templates, _without_comments

#: The kit itself: the macro file, and the page that shows the kit with invented rows.
KIT = {"ui/templates/_macros.html", "ui/templates/design_system.html"}

#: The templates that draw a list of records by hand on 12 October 2026. Only
#: shrinks: a list that moves onto `ui.data_table` leaves, and nothing joins.
HAND_DRAWN_LISTS: frozenset[str] = frozenset(
    {
        "domains/cms/templates/_cp_kaarten.html",
        "domains/designstudio/templates/_ds_lijst.html",
        "domains/forms/templates/_fb_kaarten.html",
        "domains/meetings/templates/_vg_lijst.html",
        "domains/newsletter/templates/_nb_lijst.html",
        "domains/reporting/templates/_rp_kaarten.html",
        "domains/workflow/templates/_werkbank_lijst.html",
        "ui/templates/_tn_kaarten.html",
    }
)

#: How many entries the baseline may hold. Goes down with it, never up.
CEILING = 8

_TAG = re.compile(r"{%-?\s*(for|endfor|call|endcall)\b(.*?)-?%}", re.S)


def hand_drawn_loops(text: str) -> list[str]:
    """The loop variables of every loop that draws a way in per item by hand."""
    text = _without_comments(text)
    found: list[str] = []
    calls: list[bool] = []  # per open `call`: is it the table's?
    loops: list[tuple[list[str], int, bool]] = []  # names, where the body starts, in the table
    for tag in _TAG.finditer(text):
        kind, rest = tag.groups()
        if kind == "call":
            calls.append("data_table(" in rest)
        elif kind == "endcall" and calls:
            calls.pop()
        elif kind == "for":
            names = re.findall(r"\w+", re.split(r"\s+in\s", rest, maxsplit=1)[0])
            loops.append((names, tag.end(), any(calls)))
        elif kind == "endfor" and loops:
            variables, start, in_table = loops.pop()
            body = text[start : tag.start()]
            for name in variables:
                item = re.escape(name)
                link = re.search(
                    r'href\s*=\s*"/admin/[^"{]*(?:{{\s*' + item + r'\b|"\s*~\s*' + item + r"\b)",
                    body,
                )
                if link and not in_table:
                    found.append(name)
    return found


def _read() -> dict[str, str]:
    """Every template outside the kit: path under `app/` → text."""
    return {
        path.relative_to(APP).as_posix(): path.read_text("utf-8")
        for path in sorted(APP.rglob("templates/**/*.html"))
        if path.relative_to(APP).as_posix() not in KIT
    }


def lists_by_hand() -> set[str]:
    """The templates with a loop of ways in drawn by hand (signal 2)."""
    return {name for name, text in _read().items() if hand_drawn_loops(text)}


def list_screens() -> dict[str, bool]:
    """Every screen on the list layout: file name → does its family call the table?"""
    known = _templates()
    screens = {}
    for name, path in known.items():
        if re.search(r'{%-?\s*extends\s+"list_page\.html"', path.read_text("utf-8")):
            family = _family(name, known, set())
            screens[name] = any(
                "ui.data_table(" in _without_comments(known[part].read_text("utf-8"))
                for part in family
            )
    return screens


def test_the_gate_reads_the_templates_and_recognises_lists():
    """Zero templates read, or zero lists recognised, would be green for ever."""
    read = _read()
    assert len(read) > 100, f"only {len(read)} templates read — did the folder move?"
    on_the_table = {name for name, text in read.items() if "ui.data_table(" in text}
    assert {
        "domains/mdm/templates/_leden_lijst.html",
        "domains/mdm/templates/_personen_lijst.html",
        "domains/payment/templates/_betalingen_lijst.html",
    } <= on_the_table, "the lists that are on the table are not found"
    screens = list_screens()
    assert {"leden.html", "personen.html", "betalingen.html"} <= set(screens), screens
    assert on_the_table or lists_by_hand(), "no list recognised at all"


def test_a_list_screen_draws_its_list_with_the_table():
    """Signal 1: on the list layout, the list is the kit's table."""
    without = sorted(name for name, has_table in list_screens().items() if not has_table)
    assert not without, (
        "on the list layout without ui.data_table — a list of records comes from the "
        f"kit's table (design-system-end-state §2.1): {without}"
    )


def test_no_new_list_is_drawn_by_hand():
    """Signal 2, against the baseline: nothing joins it."""
    new = sorted(lists_by_hand() - HAND_DRAWN_LISTS)
    assert not new, (
        "draws a list of records by hand (a link per item to its own back-office "
        "address) — use ui.data_table; the baseline of test_list_table_gate.py only "
        f"shrinks: {new}"
    )


def test_the_baseline_only_shrinks():
    """An entry that no longer draws a list by hand must leave, and the ceiling
    comes down with it — otherwise the room it leaves hides the next one."""
    gone = sorted(HAND_DRAWN_LISTS - lists_by_hand())
    assert not gone, f"no longer a list drawn by hand — remove from HAND_DRAWN_LISTS: {gone}"
    assert len(HAND_DRAWN_LISTS) == CEILING, (
        f"the baseline holds {len(HAND_DRAWN_LISTS)} and the ceiling says {CEILING}: "
        "lower the ceiling with the baseline; neither goes up"
    )
    assert CEILING <= 10, "the ceiling was 10 on 12 October 2026 and only comes down"


# The two screens that started this, as they stood on the builder's branch
# (12 October 2026): a card per article, an anchor with the classes written out.
CARDS = """<div class="space-y-2">
  {% for product in products %}
  <a href="/admin/ARTICLES/{{ product.id }}"
     class="block bg-surface border border-line rounded-2xl px-5 py-4 hover:bg-surface-2">
    <span class="font-semibold text-ink">{{ product.name }}</span>
    {{ ui.badge(product.status | code_label("product_status")) }}
  </a>
  {% endfor %}
</div>"""

TILES = """<div class="grid grid-cols-2 gap-3">
  {% for tile in tiles %}
  <a href="{{ tile.href }}" class="block rounded-2xl border border-line px-5 py-4">
    <span class="text-2xl font-semibold">{{ tile.value }}</span> {{ tile.label }}
  </a>
  {% endfor %}
</div>"""

FILES_OF_A_RECORD = """{% for file in attachments %}
  <a href="/admin/vergaderingen/{{ meeting.id }}/bestanden/{{ file.id }}">{{ file.name }}</a>
{% endfor %}"""

IN_THE_TABLE = """{% call ui.data_table(columns) %}
  {% for r in rows %}
  <tr>{% call ui.cell() %}<a href="/admin/leden/{{ r.id }}">{{ r.name }}</a>{% endcall %}</tr>
  {% endfor %}
{% endcall %}"""


@pytest.mark.parametrize(
    "markup",
    [
        CARDS.replace("ARTICLES", "producten"),
        CARDS.replace("ARTICLES", "prijzen"),
        CARDS.replace('"/admin/ARTICLES/{{ product.id }}"', '"/admin/producten/" ~ product.id'),
        IN_THE_TABLE + "\n" + CARDS.replace("ARTICLES", "producten"),
    ],
)
def test_the_gate_refuses_a_list_drawn_by_hand(markup, tmp_path, monkeypatch):
    """Both signals on an added template: the loop is recognised, and a screen on
    the list layout that holds it without the table is named."""
    assert hand_drawn_loops(markup) == ["product"]

    folder = tmp_path / "templates"
    folder.mkdir()
    (folder / "throwaway.html").write_text(
        '{% extends "list_page.html" %}\n{% block list_body %}' + CARDS + "{% endblock %}", "utf-8"
    )
    monkeypatch.setattr("tests.test_list_page_gate.APP", tmp_path)
    assert list_screens() == {"throwaway.html": False}


@pytest.mark.parametrize("markup", [TILES, FILES_OF_A_RECORD, IN_THE_TABLE])
def test_the_gate_leaves_what_is_no_list_alone(markup):
    assert hand_drawn_loops(markup) == []
