"""CR-11 pilot A, K1 (#1555): the list kit — key figures, status filter, toolbar, pager.

The norm is `docs/design-system-end-state.md` §2.1, §3.7, §3.8 and §3.13 (blocks 2
and 3, Koen, 2 October 2026). These tests render the macros themselves; the screen
that uses them (Betalingen) has its own tests, and the gate over the templates is
`test_list_page_gate.py`.

B7 test 18 — one figure per item: proven by passing a pair. B7 test 5 — a figure is
read, the status filter filters: a rendered figure is no link, no button and no
card; the status filter is a group of radios and never a tab bar.

Proven red (each on this branch, restored after):
- the check taken out of `KeyFigure.__post_init__` → the four "refuses" cases fail;
- the figure wrapped in an `<a>` in `ui.figures` → the "plain text" test fails;
- `role="tablist"` put on the fieldset → the status filter test fails;
- the Filters panel's body moved out of the panel, into the row → the "selects
  stand in the Filters panel" test fails (its first version sliced the panel up to
  the count and stayed green on exactly this — the slice now ends at Toepassen);
- `X-Raak-Filter` taken off the toolbar's form → the "five things" test fails;
- the count put back into `ui.pager(count=False)` → the pager test fails.
"""

from __future__ import annotations

import re

import pytest

from app.kernel.key_figure import KeyFigure
from app.ui import templates


def _render(source: str, **context) -> str:
    return templates.env.from_string('{% import "_macros.html" as ui %}' + source).render(**context)


# ── key figures (§3.8) ───────────────────────────────────────────────────────

ONE = {"value": "€ 120,00", "label": "Nog te ontvangen", "warning": True}


@pytest.mark.parametrize(
    "item",
    [
        {"value": "€ 120,00 · 3 boekingen", "label": "Nog te ontvangen"},
        {"value": "€ 120,00 € 40,00", "label": "Open"},
        {"value": ("€ 120,00", "€ 40,00"), "label": "Open"},
        {"value": "€ 120,00", "label": "Te ontvangen · te betalen"},
    ],
    ids=["value-and-count", "two-amounts", "a-pair", "two-labels"],
)
def test_a_figure_refuses_a_pair(item):
    with pytest.raises(TypeError):
        KeyFigure(**item)
    with pytest.raises(TypeError):
        _render("{{ ui.figures(items) }}", items=[ONE, item])


def test_figures_are_plain_text_one_figure_and_one_label_each():
    html = _render(
        "{{ ui.figures(items) }}",
        items=[{"value": "€ 9,00", "label": "Netto te betalen", "title": "De definitie."}, ONE],
    )
    assert re.findall(r"<dd data-figure[^>]*>([^<]*)</dd>", html) == ["€ 9,00", "€ 120,00"]
    assert re.findall(r"<dt data-figure-label[^>]*>([^<]*)</dt>", html) == [
        "Netto te betalen",
        "Nog te ontvangen",
    ]
    # Read, not clicked: no link, no button, no card, no hover.
    for piece in ("<a", "<button", "href", "hx-", "hover:", "rounded", "shadow", "bg-"):
        assert piece not in html, piece
    # The warning tint on the figure that asks for attention, and on no other.
    tints = re.findall(r'<dd data-figure class="([^"]*)"', html)
    assert ["text-brand-warning" in t for t in tints] == [False, True]
    # The full definition on hover; without one, the label.
    assert 'title="De definitie."' in html and 'title="Nog te ontvangen"' in html


# ── status filter (§3.13) ────────────────────────────────────────────────────

SEGMENTS = [
    {"value": "alle", "label": "Alle"},
    {"value": "openstaand", "label": "Openstaand", "count": 3},
    {"value": "klaar", "label": "Klaar", "count": 0},
]


def test_the_status_filter_is_a_group_of_radios_never_tabs():
    html = _render(
        '{{ ui.status_filter("zicht", segments, "openstaand", "Status", id="t") }}',
        segments=SEGMENTS,
    )
    assert html.count("<fieldset") == 1 and "<legend" in html
    radios = re.findall(r'<input type="radio" name="zicht" value="(\w+)"[^>]*?( checked)?>', html)
    assert radios == [("alle", ""), ("openstaand", " checked"), ("klaar", "")]
    for piece in ('role="tab', "<a ", "href"):
        assert piece not in html, piece
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    # A count in brackets after the name (Q54); a zero stays; "Alle" has none.
    assert "Openstaand (3)" in text and "Klaar (0)" in text
    assert "Alle (" not in text
    # Each count in its own element, so a fragment can refresh it out-of-band.
    assert 'id="t-n-openstaand"' in html and 'id="t-n-alle"' not in html


# ── toolbar (§3.13) ──────────────────────────────────────────────────────────

TOOLBAR = """{% call ui.toolbar("/lijst", "#lijst", "t", segments=segments, status_name="zicht",
     status_current="alle", status_legend="Status", q="jan", search_placeholder="Zoek",
     page=2, per_page=25, total=62, page_sizes=[25, 50, 100], menu=menu,
     hidden=[("activiteit", "7")]) %}{{ filters }}{% endcall %}"""
MENU = [{"label": "Export (.ods)", "href": "/export", "icon": "download", "with_state": True}]
SELECT = '<select name="context"><option>Alle</option></select>'


def _toolbar(filters: str = SELECT, menu=MENU) -> str:
    from markupsafe import Markup

    return _render(TOOLBAR, segments=SEGMENTS, menu=menu, filters=Markup(filters))


def test_the_toolbar_holds_five_things_in_one_order():
    html = _toolbar()
    order = [
        html.index("data-status-filter"),
        html.index("data-toolbar-search"),
        html.index("data-filters-button"),
        html.index("data-toolbar-count"),
        html.index("data-page-size"),
        html.index("data-more-button"),
    ]
    assert order == sorted(order), "status · search · Filters · count with page size · ⋯"
    assert html.count("<form") == 1, "one form sends every field together"
    assert "X-Raak-Filter" in html, "the request is not marked, so the URL keeps no state"
    assert re.search(r'id="t-count"[^>]*>\s*26–50 van 62\s*<', html)
    assert '<input type="hidden" name="activiteit" value="7">' in html
    assert 'value="jan"' in html and 'type="submit"' in html, "the magnifier is the submit"


def test_the_selects_stand_in_the_filters_panel_and_wait_for_toepassen():
    html = _toolbar()
    # The panel ends with its one Toepassen: what stands after it is the row.
    start = html.index("data-filters-panel")
    panel = html[start : html.index("</button>", html.index("Toepassen", start))]
    assert 'name="context"' in panel and "Toepassen" in panel
    outside = html.replace(panel, "")
    assert 'name="context"' not in outside, "a select stands loose in the row"
    # A change inside the panel does not send the form; Toepassen does.
    assert "change[!event.target.closest('[data-filters-panel]')" in html


def test_without_selects_there_is_no_filters_button():
    html = _toolbar(filters="")
    assert "data-filters-button" not in html and "Toepassen" not in html
    assert "data-status-filter" in html and "data-more-button" in html


def test_the_menu_holds_the_secondary_actions_and_the_page_size_for_a_phone():
    html = _toolbar()
    menu = html[html.index("data-more-menu") :]
    assert "Export (.ods)" in menu and "/export?" in menu and "new FormData" in menu
    # The page size is sent once: the phone's control has an empty name.
    assert html.count('name="per_page"') == 1
    assert 'name="" class' in menu and "data-page-size-mirror" in menu
    assert html.count("Export (.ods)") == 1, "a button stands in two places"


def test_the_out_of_band_part_refreshes_the_count_and_the_segment_counts():
    html = _render(
        '{{ ui.toolbar_oob("t", segments=segments, page=1, per_page=50, total=0) }}',
        segments=SEGMENTS,
    )
    assert re.search(r'id="t-count" hx-swap-oob="true"[^>]*>\s*0–0 van 0\s*<', html)
    assert re.findall(r'id="t-n-(\w+)" hx-swap-oob="true"[^>]*>\((\d+)\)<', html) == [
        ("openstaand", "3"),
        ("klaar", "0"),
    ]


# ── pager (§3.7) ─────────────────────────────────────────────────────────────


def test_range_text_is_the_one_wording_of_a_count():
    out = _render(
        "{{ ui.range_text(1, 50, 312) }}|{{ ui.range_text(2, 50, 62) }}|{{ ui.range_text(1, 50, 0) }}"
    )
    assert out == "1–50 van 312|51–62 van 62|0–0 van 0"


def test_the_bottom_pager_of_a_list_page_is_two_buttons_that_push_their_page():
    html = _render(
        '{{ ui.pager(1, per_page=25, total=62, hx_get="/lijst?zicht=alle", hx_target="#l",'
        " count=False, push=True) }}"
    )
    assert "Vorige" in html and "Volgende" in html
    assert "van 62" not in html, "the count stands in the toolbar, not here too"
    assert 'hx-get="/lijst?zicht=alle&page=2"' in html.replace("&amp;", "&")
    assert "X-Raak-Filter" in html
    assert 'disabled aria-disabled="true"' in html, "the first page's Vorige is disabled"
    # Everything fits: no navigation at all.
    assert (
        _render('{{ ui.pager(1, per_page=25, total=20, hx_get="/l", count=False) }}').strip() == ""
    )


def test_the_pager_of_the_other_lists_still_says_its_count():
    html = _render('{{ ui.pager(1, per_page=25, total=62, hx_get="/lijst") }}')
    assert "1–25 van 62" in html
