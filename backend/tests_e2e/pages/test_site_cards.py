"""E2E: the `{{tenants}}` placeholder shows each site as a card (#1566).

Measured from the rendered platform home, where the placeholder stands:

- 1 440 px: the cards of one account stand two in a row; the two of a row share
  their top and their height;
- 390 px: one column, each card as wide as the text column, and the page does
  not scroll sideways;
- a card is a link as a whole and does not look like a text link: no underline
  (the CMS text styles would give it one), the name in the ink colour.

Screenshots go outside the repo.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import PLATFORM  # noqa: E402

_CARDS = """() => {
  const grids = [...document.querySelectorAll('[data-tenant-sites] .grid')];
  const grid = grids.find(g => g.querySelectorAll('[data-site-card]').length >= 2);
  if (!grid) return null;
  const cards = [...grid.querySelectorAll('[data-site-card]')].map(a => {
    const b = a.getBoundingClientRect(), s = getComputedStyle(a);
    const name = a.querySelector('span');
    return {x: Math.round(b.left), y: Math.round(b.top + scrollY), w: Math.round(b.width), h: Math.round(b.height),
            tag: a.tagName, underline: s.textDecorationLine, name_colour: getComputedStyle(name).color,
            name_underline: getComputedStyle(name).textDecorationLine, weight: getComputedStyle(name).fontWeight};
  });
  const column = grid.parentElement.getBoundingClientRect();
  return {cards, column: Math.round(column.width), lists: document.querySelectorAll('[data-tenant-sites] ul').length,
          ink: getComputedStyle(document.body).color,
          page: [document.documentElement.scrollWidth, innerWidth]};
}"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _measure(browser, width: int) -> dict:
    page = browser.new_page(viewport={"width": width, "height": 900})
    page.goto(PLATFORM + "/", wait_until="networkidle")
    m = page.evaluate(_CARDS)
    page.close()
    assert m is not None, "no account with two sites on the platform home — nothing to measure"
    print("MEASURE", width, m)
    return m


def test_two_cards_of_a_row_share_their_top_and_height(browser):
    m = _measure(browser, 1440)
    first, second = m["cards"][:2]
    assert first["x"] < second["x"], "two in a row from sm"
    assert first["y"] == second["y"] and first["h"] == second["h"], (first, second)
    assert first["w"] == second["w"]
    assert m["lists"] == 0, "cards, not a bulleted list"


def test_on_a_phone_the_cards_stack_and_the_page_fits(browser):
    m = _measure(browser, 390)
    first, second = m["cards"][:2]
    assert m["page"][0] <= m["page"][1], f"the page scrolls sideways: {m['page']}"
    assert first["x"] == second["x"] and second["y"] >= first["y"] + first["h"], "one column"
    assert first["w"] == m["column"], "a card takes the text column"


def test_a_card_does_not_look_like_a_text_link(browser):
    m = _measure(browser, 1440)
    for card in m["cards"]:
        assert card["tag"] == "A", "the card is the link"
        assert card["underline"] == "none" and card["name_underline"] == "none", card
        assert card["name_colour"] == m["ink"], "the name in the ink colour, not the link colour"
        assert int(card["weight"]) >= 600
