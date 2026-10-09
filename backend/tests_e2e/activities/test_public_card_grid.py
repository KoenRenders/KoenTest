"""E2E: the activity card's actions stand where they stood, without the negative
margin (#1663; CR-11 pilot C, C1; end state §2.7).

Until #1663 the block of actions stood in the content column beside the date
tile and was pulled back over the tile on a phone by `-ml-[60px]` — the tile's
48 px plus the gap of 12, a number that had to follow the tile by hand. The card
is a grid now: on a phone the actions run over both columns, from 640 px they
stand in the content column, right under the lines beside the tile.

Geometry, so read from the rendered page (the seeded activity's card).

Red against master `a8c0e5a2` (measured, the two templates put back): at 390 the
block's margin-left is "-60px" where this asks "0px"; the positions are the same
— which is the point of C1.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, pagina_klaar  # noqa: E402

CARD = """() => {
  const title = [...document.querySelectorAll('[data-card-title] a')].find(a => a.textContent.trim() === 'E2E-activiteit');
  const card = title.closest('.rounded-2xl'), r = e => e.getBoundingClientRect();
  const tile = card.querySelector('[data-date-tile]'), actions = card.querySelector('[data-component-actions]');
  const dates = card.querySelector('[data-activity-dates]'), s = getComputedStyle(card);
  return {tile: [r(tile).left, r(tile).top, r(tile).width, r(tile).height], tag: tile.tagName,
          title: r(title.closest('[data-card-title]')).left,
          actions: [r(actions).left, r(actions).right, r(actions).top], margin: getComputedStyle(actions).marginLeft,
          inner: [r(card).left + parseFloat(s.paddingLeft) + parseFloat(s.borderLeftWidth),
                  r(card).right - parseFloat(s.paddingRight) - parseFloat(s.borderRightWidth)],
          dates_bottom: r(dates).bottom, last_line: Math.max(...[...card.querySelectorAll('[data-activity-dates] ~ p, [data-activity-dates]')].map(e => r(e).bottom)),
          page: [document.documentElement.scrollWidth, innerWidth]};
}"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _card(browser, width: int, height: int) -> dict:
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": height})
    page.goto("/activiteiten")
    pagina_klaar(page)
    measured = page.evaluate(CARD)
    page.close()
    print("MEASURE card grid", width, measured)
    return measured


def test_on_a_phone_the_actions_take_the_cards_full_width_without_a_negative_margin(browser):
    m = _card(browser, 390, 844)
    assert m["tag"] == "TIME" and m["tile"][2:] == [48, 48], m["tile"]
    assert m["margin"] == "0px", f"the block is pulled sideways by a margin of {m['margin']}"
    # From the card's inner left edge — where the tile stands — to its inner right edge.
    assert (
        abs(m["actions"][0] - m["inner"][0]) < 0.5 and abs(m["actions"][0] - m["tile"][0]) < 0.5
    ), m
    assert abs(m["actions"][1] - m["inner"][1]) < 0.5, m
    # Under the tile AND under the lines beside it, 12 px lower than the lowest of the two.
    lowest = max(m["tile"][1] + m["tile"][3], m["last_line"])
    assert abs(m["actions"][2] - lowest - 12) < 0.5, m
    assert m["page"][0] == m["page"][1]


@pytest.mark.parametrize(("width", "tile"), [(1440, 56), (768, 56), (640, 56)])
def test_from_640_the_actions_stand_in_the_content_column_under_its_lines(browser, width, tile):
    m = _card(browser, width, 900)
    assert m["tile"][2:] == [tile, tile], m["tile"]
    assert m["margin"] == "0px"
    # On the title's left line, beside the tile…
    assert abs(m["actions"][0] - m["title"]) < 0.5 and m["actions"][0] > m["tile"][0] + tile, m
    # …and 12 px under the content's last line — not under the tile, which may be higher.
    assert abs(m["actions"][2] - m["last_line"] - 12) < 0.5, m
    assert m["page"][0] == m["page"][1]
