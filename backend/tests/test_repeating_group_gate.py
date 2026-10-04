"""The kit owns the repeating group (CR-11 block 7, #1559; B7 test 1 and its new rules).

`design-system-end-state.md` §3.3. A screen that has rows — dates, components,
products, organisers — renders them with `ui.repeating_group` and `ui.group_row`
and writes no row structure of its own:

- no handle, row menu or row action in a domain template (they are the macro's);
- no up/down buttons (`ui.reorder`) in a template that has a repeating group:
  the order is the handle's and the row menu's;
- no label of its own in a row: a simple group's labels stand once, in the
  group's head, and a field's label comes from `ui.field`;
- a loop over fields outside a row is a repeated structure outside the macro
  (the closed last section, which names each component's links, is the one
  place a loop of fields may stand);
- removing a row asks no confirmation and sends nothing: the form's one save
  writes it, and "Annuleren" undoes it.

Each rule was proven red on the activity's fiche with an additive violation
(noted at the rule); the checkers keep that proof on synthetic sources.
"""

import re
from pathlib import Path

from app.ui import templates

APP = Path(__file__).resolve().parents[1] / "app"

GROUP = "ui.repeating_group("

#: What only the macros may write.
OWN_STRUCTURE = [
    (r"data-row-handle", "a drag handle of its own"),
    (r"data-row-action", "a row action of its own"),
    (r"data-row-menu", "a row menu of its own"),
    (r"data-group-row", "a row of its own"),
    (r"\bui\.reorder\(", "up/down buttons (`ui.reorder`) beside a repeating group"),
]


def _without_comments(text: str) -> str:
    return re.sub(r"\{#.*?#\}", "", text, flags=re.S)


def _domain_templates() -> dict[str, str]:
    found = {
        str(p.relative_to(APP)): _without_comments(p.read_text())
        for p in (APP / "domains").rglob("templates/**/*.html")
    }
    assert len(found) > 100, f"only {len(found)} domain templates found — the glob looks nowhere"
    return found


def _with_groups() -> dict[str, str]:
    return {rel: text for rel, text in _domain_templates().items() if GROUP in text}


def _bodies(text: str, macro: str) -> list[str]:
    """The bodies of every `{% call ui.<macro>(…) %}` … `{% endcall %}`, nested
    calls included in their parent's body."""
    bodies = []
    opening = re.compile(r"\{%-?\s*call\s+ui\.(\w+)\(.*?%\}", re.S)
    closing = re.compile(r"\{%-?\s*endcall\s*-?%\}")
    stack: list[tuple[str, int]] = []
    tokens = sorted(
        [(m.start(), m.end(), m.group(1)) for m in opening.finditer(text)]
        + [(m.start(), m.end(), None) for m in closing.finditer(text)]
    )
    for start, end, name in tokens:
        if name is not None:
            stack.append((name, end))
        elif stack:
            opened, body_start = stack.pop()
            if opened == macro:
                bodies.append(text[body_start:start])
    return bodies


# ── The checkers ─────────────────────────────────────────────────────────────


def own_structure(rel: str, text: str) -> list[str]:
    return [f"{rel}: {what}" for pattern, what in OWN_STRUCTURE if re.search(pattern, text)]


def labels_in_rows(rel: str, text: str) -> list[str]:
    found = []
    for body in _bodies(text, "group_row"):
        if re.search(r"<label\b|\bui\.label\(|\bui\.inline_label\(", body):
            found.append(
                f"{rel}: a label of its own in a row — the group's head or `ui.field` carries it"
            )
    return found


def fields_looped_outside_a_row(rel: str, text: str) -> list[str]:
    """A `{% for %}` whose body calls `ui.field(` without a row around it."""
    stripped = text
    for macro in ("group_row", "rare_settings"):
        for body in _bodies(text, macro):
            stripped = stripped.replace(body, "")
    found = []
    for loop in re.findall(r"\{%-?\s*for\b.*?%\}(.*?)\{%-?\s*endfor\s*-?%\}", stripped, re.S):
        if "ui.field(" in loop:
            found.append(
                f"{rel}: fields in a loop outside `ui.group_row` — a repeated structure outside the macro"
            )
    return found


# ── The rules on the real templates ──────────────────────────────────────────


def test_the_gate_finds_the_groups():
    """A gate that finds nothing is green forever: the activity's fiche has four
    groups (dates, components, products, organisers)."""
    groups = _with_groups()
    assert "domains/activities/templates/_aa_detail.html" in groups, sorted(groups)
    assert groups["domains/activities/templates/_aa_detail.html"].count(GROUP) >= 4


def test_no_screen_writes_a_row_structure_of_its_own():
    """Proven red by adding `{{ ui.reorder() }}` to `_aa_detail.html`, and by a
    raw `<span data-row-handle>` in it."""
    found = [v for rel, text in _with_groups().items() for v in own_structure(rel, text)]
    assert found == []


def test_a_row_carries_no_label_of_its_own():
    """Proven red by adding `{{ ui.label("Datum", "x") }}` inside the date row."""
    found = [v for rel, text in _with_groups().items() for v in labels_in_rows(rel, text)]
    assert found == []


def test_no_fields_are_looped_outside_a_row():
    found = [
        v for rel, text in _with_groups().items() for v in fields_looped_outside_a_row(rel, text)
    ]
    assert found == []


# ── The macros themselves ────────────────────────────────────────────────────


def _render(body: str, **ctx) -> str:
    return templates.env.from_string("{% import '_macros.html' as ui %}" + body).render(**ctx)


ROW = "{% call ui.group_row('d_order', key, edit=edit, variant=variant, handle=handle, menu=menu, title='Wandeling') %}{{ ui.field('d.' ~ key ~ '.x', 'Datum', kind='date', span='quarter') }}{% endcall %}"


def _row(**kwargs) -> str:
    return _render(
        ROW,
        **{
            "key": "7",
            "edit": True,
            "variant": "simple",
            "handle": True,
            "menu": ["up", "down", "duplicate", "remove"],
            **kwargs,
        },
    )


def test_removing_a_row_asks_nothing_and_sends_nothing():
    """Decision 07: inside an unsaved form "Annuleren" undoes a removal; the
    kit's dialog is for deleting a record. Proven red with `data-confirm` on the
    remove item of `_row_menu`."""
    html = _row()
    remove = re.search(r'<button[^>]*data-row-action="remove"[^>]*>', html).group(0)
    assert "confirm" not in remove and "hx-" not in remove
    assert 'type="button"' in remove and "text-red-700" in remove
    menu = html[html.index("data-row-menu") :]
    actions = re.findall(r'data-row-action="(\w+)"', menu)
    assert actions == ["up", "down", "duplicate", "remove"], "Verwijderen last, after a divider"
    assert menu.index("border-t") < menu.index('data-row-action="remove"')


def test_a_row_offers_only_what_its_group_offers():
    members = _row(menu=["up", "down", "remove"])
    assert 'data-row-action="duplicate"' not in members, "a member is not duplicated"
    unordered = _row(handle=False, menu=["duplicate", "remove"])
    assert "data-row-handle" not in unordered and 'data-row-action="up"' not in unordered


def test_read_mode_has_no_handle_no_menu_and_no_order_field():
    html = _row(edit=False)
    for edits in ("data-row-handle", "data-row-menu", "data-row-order", 'name="d_order"'):
        assert edits not in html, edits
    assert "data-group-row" in html


def test_a_row_names_its_place_with_an_order_field():
    html = _row()
    assert '<input type="hidden" name="d_order" value="7" data-row-order>' in html
    assert 'data-row-key="7"' in html


def test_a_composite_item_has_its_handle_before_its_body_and_its_menu_on_the_title_line():
    """The gutter: the handle is a sibling BEFORE the body, never inside it, so
    title and fields share the edge to its right (Q50)."""
    html = _row(variant="composite")
    assert (
        html.index("data-row-handle")
        < html.index("data-row-body")
        < html.index("data-row-title-line")
    )
    title = html[html.index("data-row-title-line") : html.index("data-field")]
    assert "Wandeling" in title and "data-row-menu-trigger" in title
    body = html[html.index("data-row-body") :]
    assert "data-row-handle" not in body


GROUP_CALL = (
    "{% call ui.repeating_group('Datums', 'd_order', token='__D__', add_label='Datum', edit=edit, empty='Nog geen datums.',"
    " count=count, template='<div>__D__</div>', columns=[{'label': 'Datum', 'span': 'quarter', 'required': True}, {'label': 'Van', 'span': 'quarter'}]) %}"
    "{% endcall %}"
)


def test_the_group_adds_only_in_edit_mode_and_says_when_it_is_empty():
    edit = _render(GROUP_CALL, edit=True, count=0)
    assert "data-group-add" in edit and "<template data-group-template>" in edit
    assert re.search(r"<p data-group-empty[^>]*>Nog geen datums\.</p>", edit)
    assert " hidden" not in re.search(r"<p data-group-empty[^>]*>", edit).group(0)
    assert " hidden" in re.search(r"<div data-group-head[^>]*>", edit).group(0), (
        "no head over no rows"
    )
    filled = _render(GROUP_CALL, edit=True, count=2)
    assert " hidden" in re.search(r"<p data-group-empty[^>]*>", filled).group(0)
    head = filled[filled.index("data-group-head") : filled.index("data-group-rows")]
    assert head.count("data-span") == 2 and ">Datum " in head and ">Van<" in head

    read = _render(GROUP_CALL, edit=False, count=2)
    for edits in ("data-group-add", "<template", "data-group-head"):
        assert edits not in read, edits


def test_a_child_group_is_no_card():
    html = _render(
        "{% call ui.repeating_group('Producten', 'p_order.3', child=True, edit=True, add_label='Product', variant='composite') %}{% endcall %}"
    )
    opening = html[: html.index(">") + 1]
    assert 'class="group-child"' in opening and "<div " in opening
    assert "rounded" not in opening and "shadow" not in opening and "bg-" not in opening
    assert "<h3" in html and "<h2" not in html


# ── The red proofs, kept ─────────────────────────────────────────────────────

CLEAN = (
    "{% call ui.repeating_group('Datums', 'd_order') %}"
    "{% for d in dates %}{% call ui.group_row('d_order', d.id) %}{{ ui.field('d.x', 'Datum') }}{% endcall %}{% endfor %}"
    "{% endcall %}"
    "{% call ui.rare_settings('Extern') %}{% for c in comps %}{{ ui.field('c.x', 'URL', kind='url') }}{% endfor %}{% endcall %}"
)


def test_a_clean_screen_passes():
    assert own_structure("x.html", CLEAN) == []
    assert labels_in_rows("x.html", CLEAN) == []
    assert fields_looped_outside_a_row("x.html", CLEAN) == []


def test_up_and_down_buttons_beside_a_group_are_red():
    assert own_structure("x.html", CLEAN + "{{ ui.reorder(up_attrs='x') }}") == [
        "x.html: up/down buttons (`ui.reorder`) beside a repeating group"
    ]
    assert own_structure("x.html", CLEAN + "<span data-row-handle></span>") == [
        "x.html: a drag handle of its own"
    ]


def test_a_label_in_a_row_is_red():
    source = CLEAN.replace(
        "{{ ui.field('d.x', 'Datum') }}",
        "{{ ui.label('Datum', 'x') }}{{ ui.field('d.x', 'Datum') }}",
    )
    assert labels_in_rows("x.html", source) == [
        "x.html: a label of its own in a row — the group's head or `ui.field` carries it"
    ]


def test_fields_in_a_loop_outside_a_row_are_red():
    source = CLEAN + "{% for d in dates %}{{ ui.field('d.y', 'Datum') }}{% endfor %}"
    assert fields_looped_outside_a_row("x.html", source) == [
        "x.html: fields in a loop outside `ui.group_row` — a repeated structure outside the macro"
    ]
