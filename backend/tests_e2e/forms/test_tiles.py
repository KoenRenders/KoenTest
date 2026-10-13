"""E2E: a choice of one among tiles, on the kit's own page (#1967).

Measured from the rendered boxes of `/admin/design-system`, section 13b′:

- four tiles per row under 768 px and six from there, every tile as wide as the
  others and at least 44 px high, the last row packed left; thirteen options
  without a sideways scroll at 390 px;
- a click and the keyboard choose a tile and never the one that is not
  choosable; what the form submits is read from the address it sends to;
- a required choice is asked for before the form leaves;
- the chosen tile shows its check mark, the unavailable one its reason.

Broken on purpose (13 October 2026, each put back):
- `grid-cols-4` made `grid-cols-5` in the macro → "4 per row at 390 px";
- `disabled` taken off the unavailable radio → the click chooses it: "a click
  chose the tile that is not choosable";
- the check mark's `peer-checked:inline-flex` taken out → "the chosen tile has
  no mark beside its colour".
"""

import os
import sys
from urllib.parse import parse_qs, urlsplit

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

_TILES = """name => {
  const field = document.querySelector(`[data-field="${name}"]`);
  const tiles = [...field.querySelectorAll('[data-tile]')].map(t => {
    const b = t.getBoundingClientRect(), i = t.querySelector('input');
    const mark = t.querySelector('[data-tile-check]'), why = t.querySelector('[data-tile-reason]');
    return {value: i.value, x: Math.round(b.left * 10) / 10, y: Math.round(b.top + scrollY),
            w: Math.round(b.width * 10) / 10, h: Math.round(b.height * 10) / 10,
            checked: i.checked, disabled: i.disabled, mark: !!mark && mark.checkVisibility(),
            why: why ? why.textContent.trim() : null,
            described: i.getAttribute('aria-describedby') === (why ? why.id : null) || !why,
            struck: !!why && getComputedStyle(t.querySelector('span')).textDecorationLine.includes('line-through')};
  });
  const grid = field.querySelector('[data-tiles]').getBoundingClientRect();
  return {tiles, grid: [Math.round(grid.left * 10) / 10, Math.round(grid.width * 10) / 10],
          page: [document.documentElement.scrollWidth, innerWidth]};
}"""


@pytest.fixture(scope="module")
def browser():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


def _page(browser, width: int):
    b, session = browser
    page = b.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    login_met_sessie(page, session)
    page.goto("/admin/design-system")
    pagina_klaar(page)
    return page


def _rows(tiles: list[dict]) -> list[list[dict]]:
    rows: dict[int, list[dict]] = {}
    for tile in tiles:
        rows.setdefault(tile["y"], []).append(tile)
    return [rows[y] for y in sorted(rows)]


def _chosen(page, name: str) -> str | None:
    return page.evaluate(
        'n => (document.querySelector(`[data-field="${n}"] input:checked`) || {}).value || null',
        name,
    )


def _click_tile(page, name: str, value: str) -> None:
    """A click where a person clicks: the middle of the tile, with the mouse."""
    tile = page.locator(f'[data-field="{name}"] [data-tile]:has(input[value="{value}"])')
    tile.scroll_into_view_if_needed()
    box = tile.bounding_box()
    page.mouse.click(box["x"] + box["width"] / 2, box["y"] + box["height"] / 2)


@pytest.mark.parametrize(("width", "per_row"), [(390, 4), (1440, 6)])
def test_the_grid_is_four_then_six_tiles_of_one_width(browser, width, per_row):
    page = _page(browser, width)
    for name, count in (("kit_tiles_thirteen", 13), ("kit_tiles_none", 6), ("kit_tiles_single", 1)):
        seen = page.evaluate(_TILES, name)
        tiles = seen["tiles"]
        rows = _rows(tiles)
        print(
            "MEASURE tiles",
            width,
            name,
            [len(r) for r in rows],
            tiles[0]["w"],
            tiles[0]["h"],
            seen["grid"],
            seen["page"],
        )
        assert len(tiles) == count
        assert seen["page"][0] <= seen["page"][1], (
            f"a sideways scroll at {width} px: {seen['page']}"
        )
        expected = [per_row] * (count // per_row) + ([count % per_row] if count % per_row else [])
        assert [len(r) for r in rows] == expected, f"{per_row} per row at {width} px"
        widths = {t["w"] for t in tiles}
        assert max(widths) - min(widths) <= 0.5, f"tiles of unequal width: {sorted(widths)}"
        assert min(t["h"] for t in tiles) >= 44, "a tile under the touch height"
        # Every row starts on the grid's left edge, the last one too: packed left.
        assert {r[0]["x"] for r in rows} == {seen["grid"][0]}, "a row does not start at the left"
        gaps = {round(b["x"] - a["x"] - a["w"], 1) for r in rows for a, b in zip(r, r[1:])}
        assert all(abs(g - 8) <= 0.2 for g in gaps), (
            f"the gap between two tiles is not 8 px: {gaps}"
        )
        # The tiles fill the row: per_row widths and the gaps are the grid's width.
        assert abs(per_row * tiles[0]["w"] + (per_row - 1) * 8 - seen["grid"][1]) <= 1
    page.close()


def test_the_chosen_tile_has_its_mark_and_the_unavailable_one_its_reason(browser):
    page = _page(browser, 390)
    tiles = {t["value"]: t for t in page.evaluate(_TILES, "kit_tiles_sold")["tiles"]}
    assert tiles["s"]["checked"] and tiles["s"]["mark"], (
        "the chosen tile has no mark beside its colour"
    )
    assert [v for v, t in tiles.items() if t["mark"]] == ["s"]
    sold = tiles["l"]
    assert (
        sold["disabled"] and sold["why"] == "uitverkocht" and sold["described"] and sold["struck"]
    )
    assert not sold["checked"] and [v for v, t in tiles.items() if t["disabled"]] == ["l"]
    # What a screen reader is given: a radio that is unavailable, with its reason.
    said = page.locator('[data-field="kit_tiles_sold"] input[value="l"]').aria_snapshot()
    print("MEASURE aria", said)
    assert "radio" in said and "disabled" in said and "uitverkocht" in said
    page.close()


def test_a_click_and_the_keyboard_choose_a_tile_and_never_the_unavailable_one(browser):
    page = _page(browser, 390)
    name = "kit_tiles_sold"
    assert _chosen(page, name) == "s"
    _click_tile(page, name, "xl")
    assert _chosen(page, name) == "xl", "a click on a tile did not choose it"
    _click_tile(page, name, "l")
    assert _chosen(page, name) == "xl", "a click chose the tile that is not choosable"
    # The keyboard, as in any radio group: from M to the right, over L, to XL.
    _click_tile(page, name, "m")
    page.keyboard.press("ArrowRight")
    assert _chosen(page, name) == "xl", "the arrow did not step over the unavailable tile"
    page.keyboard.press("ArrowLeft")
    assert _chosen(page, name) == "m"
    seen = []
    for _ in range(7):
        page.keyboard.press("ArrowRight")
        seen.append(_chosen(page, name))
    assert "l" not in seen and set(seen) == {"xs", "s", "m", "xl", "xxl"}, seen
    page.close()


def test_a_required_choice_is_asked_for_and_one_value_is_submitted(browser):
    page = _page(browser, 390)
    send = page.locator("#kit-tiles button[type=submit]")
    send.scroll_into_view_if_needed()
    # The browser's own check, the one a click on the button runs first.
    assert page.evaluate("document.querySelector('#kit-tiles').checkValidity()") is False, (
        "the form would leave without the required choice"
    )
    missing = page.evaluate(
        "[...document.querySelectorAll('#kit-tiles :invalid')].map(e => e.name)"
    )
    assert set(missing) == {"kit_tiles_none"}, missing

    _click_tile(page, "kit_tiles_none", "xs")
    _click_tile(page, "kit_tiles_sold", "l")  # not choosable: "s" stays
    # Read from the request itself: the shell sends a form without a page load.
    with page.expect_request(lambda r: "kit_tiles" in r.url) as request:
        send.click()
    sent = parse_qs(urlsplit(request.value.url).query)
    print("MEASURE submitted", sent)
    assert sent == {
        "kit_tiles_none": ["xs"],
        "kit_tiles_chosen": ["m"],
        "kit_tiles_sold": ["s"],
        "kit_tiles_thirteen": ["41"],
    }, "one value per field with a choice, nothing of an unavailable tile, nothing unchosen"
    page.close()
