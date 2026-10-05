"""The repeating group's two shapes of #1590: a composite row that folds, and a
group in which one row is the main one (end state §3.3; `ui.repeating_group`,
`ui.group_row`).

Rendered from the macros, so what a screen gets is pinned where it is made. What
the page then does with it — the tag moving, a refusal opening a folded row — is
measured in a browser (`tests_e2e/test_household_pages.py`).

Each test was proven red by taking its subject out of the macro; the docstring
says which.
"""

from __future__ import annotations

import re

from app.ui import templates

ONE = '{"chosen": %s, "tag": "hoofdadres", "make": "Maak hoofdadres"}'


def _render(source: str) -> str:
    return templates.env.from_string("{% import '_macros.html' as ui %}" + source).render()


def _row(**kw) -> str:
    args = ", ".join(f"{k}={v}" for k, v in kw.items())
    return _render(
        '{% call ui.group_row("h_order", "7", ' + args + ") %}<p data-inside>x</p>{% endcall %}"
    )


def _menu_items(html: str) -> dict[str, bool]:
    """action → is it hidden."""
    return {
        m.group(1): " hidden" in m.group(0)
        for m in re.finditer(r'<button[^>]*data-row-action="(\w+)"[^>]*>', html)
    }


# ── A composite row that folds ───────────────────────────────────────────────


def test_a_folded_row_is_a_details_whose_summary_is_the_title_line():
    """Proven red by rendering the `fold` branch without `<details>`."""
    html = _row(edit="True", variant='"composite"', fold='"closed"', title='"Sam Peeters"')
    details = re.search(r"<details[^>]*>", html)
    assert details and "data-row-fold" in details.group(0)
    assert " open" not in details.group(0), "a row asked closed stands open"
    summary = html[html.index("<summary") : html.index("</summary>")]
    assert "data-row-title-line" in summary and "Sam Peeters" in summary
    # the fields are the details' content, after the summary — so a closed row
    # still sends them, and the browser shows them when it opens
    assert html.index("</summary>") < html.index("data-inside") < html.index("</details>")


def test_an_open_row_stands_open_and_carries_the_prefix_and_the_subtitle():
    """Proven red by dropping `open` from the details."""
    html = _row(
        edit="False",
        variant='"composite"',
        fold='"open"',
        title='"Lore Peeters"',
        title_prefix='"Hoofdlid"',
        subtitle='"Persoonsgegevens"',
    )
    assert re.search(r"<details[^>]* open", html)
    assert re.search(r"<span data-row-title-prefix>Hoofdlid</span>\s*·", html)
    assert "Persoonsgegevens" in html
    assert "data-row-menu-trigger" not in html, "read mode shows a row menu"


def test_the_menu_of_a_folded_row_stands_outside_the_summary():
    """A button inside a `<summary>` would fold the row when it is pressed.
    Proven red by rendering the menu inside the summary."""
    html = _row(edit="True", variant='"composite"', fold='"open"', title='"Sam"', menu='["remove"]')
    assert "data-row-menu-trigger" in html
    assert html.index("</details>") < html.index("data-row-menu-trigger")
    assert "group-fold--menu" in html, "the summary keeps no room for the menu"


def test_a_row_without_a_menu_keeps_no_room_for_one():
    html = _row(edit="True", variant='"composite"', fold='"open"', title='"Lore"', menu="[]")
    assert "data-row-menu-trigger" not in html
    assert "group-fold--menu" not in html


def test_a_composite_row_without_fold_is_unchanged():
    """The activity's components and products: no details, the title line a div."""
    html = _row(edit="True", variant='"composite"', title='"Wandeling"')
    assert "<details" not in html and "<summary" not in html
    assert re.search(r"<div data-row-title-line", html)


# ── One among many ───────────────────────────────────────────────────────────


def test_the_group_carries_the_choice_in_one_hidden_field():
    """Proven red by leaving the field out: the save could not know the choice."""
    html = _render(
        '{% call ui.repeating_group("E-mailadressen", "e_order.7", edit=True, child=True, count=1,'
        ' one={"name": "e_primary.7", "value": "31"}) %}{% endcall %}'
    )
    assert re.search(r'<input type="hidden" name="e_primary\.7" value="31" data-group-one>', html)
    read = _render(
        '{% call ui.repeating_group("E-mailadressen", "e_order.7", edit=False, child=True, count=1,'
        ' one={"name": "e_primary.7", "value": "31"}) %}{% endcall %}'
    )
    assert "data-group-one" not in read, "read mode sends a choice"


def test_the_chosen_row_shows_the_tag_and_cannot_be_removed():
    """Proven red by showing "Verwijderen" on the chosen row."""
    html = _row(edit="True", menu='["remove"]', one=ONE % "True")
    tag = re.search(r"<span data-row-one-tag[^>]*>", html)
    assert tag and " hidden" not in tag.group(0)
    assert "hoofdadres" in html
    assert _menu_items(html) == {"choose": True, "remove": True}
    holder = re.search(r"<div[^>]*data-row-menu-holder[^>]*>", html)
    assert holder and " hidden" in holder.group(0), "a menu with nothing in it is offered"


def test_another_row_offers_to_take_the_tag_over_and_can_be_removed():
    """Proven red by hiding "Maak hoofdadres" on every row."""
    html = _row(edit="True", menu='["remove"]', one=ONE % "False")
    tag = re.search(r"<span data-row-one-tag[^>]*>", html)
    assert tag and " hidden" in tag.group(0), "the tag shows on a row that is not chosen"
    assert _menu_items(html) == {"choose": False, "remove": False}
    assert "Maak hoofdadres" in html
    holder = re.search(r"<div[^>]*data-row-menu-holder[^>]*>", html)
    assert holder and " hidden" not in holder.group(0)


def test_the_tag_shows_in_read_mode_too():
    html = _row(edit="False", one=ONE % "True")
    tag = re.search(r"<span data-row-one-tag[^>]*>", html)
    assert tag and " hidden" not in tag.group(0)
    assert "data-row-action" not in html


def test_a_row_of_an_ordinary_group_carries_no_tag_and_no_choice():
    html = _row(edit="True", menu='["remove"]')
    assert "data-row-one-tag" not in html
    assert _menu_items(html) == {"remove": False}
