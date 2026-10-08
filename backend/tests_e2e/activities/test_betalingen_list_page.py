"""E2E: Betalingen on the `list_page` layout (CR-11 pilot A, K1 — #1555).

Measured in the browser, because the acceptance of K1 is geometry and behaviour
that no template test sees: where the first row starts, whether the toolbar is
one row, what a click on a segment yields, and whether the way back from a
booking finds the list as it was left.

- **The first row starts on the first screen** (CR-11 B7 test 23; acceptance):
  at 1 920 × 1 080 and 1 440 × 900 its top is at y ≤ 360, at 390 × 844 it is
  inside the viewport. (ChatGPT's prototype of brief 03 measured 260, 252 and
  435 with three rows of chrome less: no shell banner, no meta line.)
- **The toolbar is one row on a desktop and three lines on a phone**, the same
  five things in the same order; the search is 180–480 px wide; a segment is
  36 px high, 44 on a phone.
- **No row of controls widens the page** (B7 test 22).
- **Figures on one line, the title first** (B7 test 20): one line per label, no
  label cut, the figures of one line on one baseline.
- **Filters** opens a panel with the context select and Toepassen; the select
  waits for Toepassen. **⋯** holds Export, and no button stands twice.
- **"Openstaand (n)" counts what the click yields**, also with a search term.
- **Back to the list as it was** (B7 test 21, R14): segment and search term
  come back from a booking's registration.

The seed holds five registration groups, three of them open; other e2e files
add bookings in the same run, so the counts are read from the screen and
compared with each other, not with a fixed number. Nothing here changes data.

Proven red (on this branch, restored after): the selects moved out of the
Filters panel into the row → the Filters test and the three geometry tests fail;
`X-Raak-Filter` taken off the toolbar → the way-back, the count, the Filters and
the page-size tests fail (the URL keeps no state); the segment's count computed
without the search → the count test fails; a figure label given a width of 64 px
→ the three label tests fail (a real label is cut).
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_afgerond, login_met_sessie, pagina_klaar  # noqa: E402

DESKTOPS = [(1920, 1080), (1440, 900)]
PHONE = (390, 844)

_GEOMETRY = """() => {
  const box = s => { const e = document.querySelector(s); if (!e || !e.checkVisibility()) return null;
    const r = e.getBoundingClientRect(); return {x: r.left, y: r.top, w: r.width, h: r.height}; };
  const row = document.querySelector('#betalingen-lijst tbody tr');
  return {
    title: box('[data-list-head] h1'), figures: box('[data-figures]'),
    figure_tops: [...document.querySelectorAll('[data-figure]')].map(e => Math.round(e.getBoundingClientRect().top)),
    labels: [...document.querySelectorAll('[data-figure-label]')].map(e => ({
      text: e.innerText, scroll: e.scrollWidth, client: e.clientWidth,
      h: e.getBoundingClientRect().height, line: parseFloat(getComputedStyle(e).lineHeight)})),
    figure_links: document.querySelectorAll('[data-figures] a, [data-figures] button').length,
    toolbar: box('[data-toolbar]'), status: box('[data-status-filter]'),
    search: box('[data-toolbar-search]'), filters: box('[data-filters-button]'),
    count: box('[data-toolbar-count]'), size: box('[data-page-size]'), more: box('[data-more-button]'),
    first_row_y: row ? row.getBoundingClientRect().top : null,
    scroll: document.documentElement.scrollWidth, width: innerWidth, height: innerHeight,
    tablists: document.querySelectorAll('#main [role=tablist]').length,
    loose_selects: document.querySelectorAll('[data-toolbar] > select:not([data-page-size])').length,
  };
}"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _open(browser, size, url="/admin/betalingen"):
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    page = browser.new_page(base_url=BASE, viewport={"width": size[0], "height": size[1]})
    login_met_sessie(page, make_session_value(SEEDED_ADMIN_EMAIL), BASE)
    page.goto(url)
    pagina_klaar(page)
    return page


def _count(page) -> str:
    return page.locator("[data-toolbar-count]").inner_text().strip()


def _segment(page, value: str) -> str:
    return " ".join(
        page.locator(f"[data-status-filter] label:has(input[value={value}])").inner_text().split()
    )


@pytest.mark.parametrize("size", DESKTOPS, ids=["1920", "1440"])
def test_on_a_desktop_the_toolbar_is_one_row_and_the_first_row_is_in_the_top_third(browser, size):
    page = _open(browser, size)
    g = page.evaluate(_GEOMETRY)
    print("MEASURE", size[0], g)
    page.close()

    assert g["first_row_y"] is not None and g["first_row_y"] <= 360, g["first_row_y"]
    # One row: every one of the five things lies within the toolbar's one line.
    parts = [g[k] for k in ("status", "search", "filters", "count", "size", "more")]
    assert all(parts), "one of the five things is missing"
    assert g["toolbar"]["h"] <= 44, f"the toolbar wrapped: {g['toolbar']}"
    xs = [p["x"] for p in parts]
    assert xs == sorted(xs), "status · search · Filters · count · page size · ⋯"
    assert 180 <= g["search"]["w"] <= 480, g["search"]
    assert g["status"]["h"] == 36, g["status"]
    # The title, then the figures, on one row.
    assert g["title"]["x"] < g["figures"]["x"]
    assert (
        abs((g["title"]["y"] + g["title"]["h"] / 2) - (g["figures"]["y"] + g["figures"]["h"] / 2))
        <= 4
    )
    assert max(g["figure_tops"]) - min(g["figure_tops"]) <= 1, g["figure_tops"]
    assert g["scroll"] == g["width"]
    assert g["tablists"] == 0 and g["loose_selects"] == 0 and g["figure_links"] == 0


def test_on_a_phone_three_toolbar_lines_and_the_first_row_on_the_first_screen(browser):
    page = _open(browser, PHONE)
    g = page.evaluate(_GEOMETRY)
    print("MEASURE", PHONE[0], g)
    page.close()

    assert g["first_row_y"] is not None and 0 < g["first_row_y"] < g["height"], g["first_row_y"]
    # Three lines: the status filter, the search, then Filters · count · ⋯.
    assert g["status"]["y"] < g["search"]["y"] < g["filters"]["y"]
    for part in ("count", "more"):
        assert (
            abs((g[part]["y"] + g[part]["h"] / 2) - (g["filters"]["y"] + g["filters"]["h"] / 2))
            <= 2
        )
    assert g["filters"]["x"] < g["count"]["x"] < g["more"]["x"]
    assert g["size"] is None, "the page size stands in the row on a phone; it belongs under ⋯"
    assert g["status"]["h"] == 44 and g["more"]["h"] == 44, "a phone's touch target is 44 px"
    assert g["status"]["w"] == g["search"]["w"] == g["toolbar"]["w"]
    # The title first, the figures under it; within one line, one baseline.
    assert g["figures"]["y"] >= g["title"]["y"] + g["title"]["h"]
    by_line: dict[int, int] = {}
    for top in g["figure_tops"]:
        by_line[top] = by_line.get(top, 0) + 1
    assert len(by_line) <= 2, f"the figures take more than two lines: {g['figure_tops']}"
    assert g["scroll"] == g["width"], "a row of controls widens the page"


@pytest.mark.parametrize("size", [*DESKTOPS, PHONE], ids=["1920", "1440", "390"])
def test_every_figure_label_is_one_line_and_none_is_cut(browser, size):
    page = _open(browser, size)
    g = page.evaluate(_GEOMETRY)
    page.close()

    assert [label["text"] for label in g["labels"]] == [
        "Netto te betalen",
        "Nog te ontvangen",
        "Nog terug te betalen",
    ]
    for label in g["labels"]:
        assert label["h"] == label["line"], f"not one line: {label}"
        assert label["scroll"] <= label["client"], f"a real label is cut: {label}"


def test_filters_is_a_panel_and_its_select_waits_for_toepassen(browser):
    page = _open(browser, DESKTOPS[1])
    panel = page.locator("[data-filters-panel]")
    assert not panel.is_visible()
    before = _count(page)

    page.locator("[data-filters-button]").click()
    panel.wait_for(state="visible")
    assert panel.locator("select[name=context]").count() == 1
    assert panel.get_by_role("button", name="Toepassen").count() == 1
    # A change that sent the form would start its request at once (the form's
    # `change` trigger has no delay): none started, so the select waits.
    asked = []
    page.on(
        "request", lambda r: asked.append(r.url) if "/admin/betalingen/lijst" in r.url else None
    )
    panel.locator("select[name=context]").select_option("membership")
    page.evaluate("() => new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    assert not asked and "context=" not in page.url, f"the select did not wait: {asked}"
    assert _count(page) == before

    with htmx_afgerond(page):
        panel.get_by_role("button", name="Toepassen").click()
    assert "context=membership" in page.url
    assert _count(page) != before, "Toepassen did not filter"
    assert not panel.is_visible()
    page.close()


def test_the_menu_holds_export_and_no_button_stands_twice(browser):
    page = _open(browser, DESKTOPS[1], "/admin/betalingen?zicht=openstaand")
    assert page.get_by_text("Export (.ods)").count() == 1
    assert not page.get_by_text("Export (.ods)").is_visible(), "Export stands outside ⋯"

    page.locator("[data-more-button]").click()
    page.get_by_role("menuitem", name="Export (.ods)").wait_for(state="visible")
    with page.expect_download() as download:
        page.get_by_role("menuitem", name="Export (.ods)").click()
    # What the list shows is what the file holds: the segment travels.
    assert (
        "/admin/betalingen/export?" in download.value.url
        and "zicht=openstaand" in download.value.url
    )
    page.close()


def test_the_count_on_openstaand_is_what_the_click_yields_also_with_a_search(browser):
    def n(page) -> int:
        return int(_segment(page, "openstaand").removeprefix("Openstaand (").removesuffix(")"))

    page = _open(browser, DESKTOPS[1])
    whole = n(page)
    assert whole >= 1, "no open booking left in this run, so this proves nothing"
    assert _segment(page, "alle") == "Alle"

    # Counted with the search of this moment — before the click. A term that
    # matches nothing brings the count to zero, and a zero stays on the segment.
    with htmx_afgerond(page):
        page.locator("input[name=q]").fill("zzz-geen-treffer")
    assert _segment(page, "openstaand") == "Openstaand (0)"
    with htmx_afgerond(page):
        page.locator("input[name=q]").fill("")
    assert n(page) == whole

    # And the count is what the click yields.
    with htmx_afgerond(page):
        page.locator("[data-status-filter] label:has(input[value=openstaand])").click()
    assert _count(page) == f"1–{whole} van {whole}"
    assert "zicht=openstaand" in page.url
    page.close()


def test_the_arrows_choose_a_segment(browser):
    page = _open(browser, DESKTOPS[1])
    page.locator("[data-status-filter] input[value=alle]").focus()
    with htmx_afgerond(page):
        page.keyboard.press("ArrowRight")
    assert page.locator("[data-status-filter] input[value=openstaand]").is_checked()
    n = int(_segment(page, "openstaand").removeprefix("Openstaand (").removesuffix(")"))
    assert _count(page) == f"1–{n} van {n}"
    assert "zicht=openstaand" in page.url
    page.close()


def test_back_from_a_booking_finds_the_list_as_it_was_left(browser):
    page = _open(browser, DESKTOPS[1])
    with htmx_afgerond(page):
        page.locator("[data-status-filter] label:has(input[value=openstaand])").click()
    with htmx_afgerond(page):
        page.locator("input[name=q]").fill("Marie")
    left_at = page.url
    rows = page.locator("#betalingen-lijst tbody tr").count()
    assert "zicht=openstaand" in left_at and "q=Marie" in left_at
    assert _count(page) == "1–1 van 1"

    # K2 (#1556): "Inschrijving openen" stands under the row's ⋯. The record it
    # opens is led back to the list as it was left, with the booking it came
    # from named in the address (`boeking=`, #1557) — the list's own state is
    # unchanged. (The row itself opens the booking's page, and from there the
    # way back is the exact address: `test_betalingen_table.py`.)
    page.locator("#betalingen-lijst [data-row-menu-trigger]").first.click()
    item = (
        page.locator("#betalingen-lijst").get_by_role("menuitem", name="Inschrijving openen").first
    )
    item.wait_for(state="visible")
    item.click()
    pagina_klaar(page)
    assert "/admin/inschrijvingen/" in page.url
    page.locator("a[href^='/admin/betalingen?']").first.click()
    pagina_klaar(page)

    assert page.url.startswith(left_at + "&boeking="), "the way back lost the list's state"
    assert page.locator("[data-status-filter] input[value=openstaand]").is_checked()
    assert page.locator("input[name=q]").input_value() == "Marie"
    assert _count(page) == "1–1 van 1"
    assert page.locator("#betalingen-lijst tbody tr").count() == rows
    page.close()


def test_on_a_phone_the_page_size_is_chosen_under_the_menu(browser):
    page = _open(browser, PHONE)
    page.locator("[data-more-button]").click()
    mirror = page.locator("[data-page-size-mirror]")
    mirror.wait_for(state="visible")
    with htmx_afgerond(page):
        mirror.select_option("25")
    assert "per_page=25" in page.url
    assert page.url.count("per_page=") == 1, "the page size was sent twice"
    page.close()
