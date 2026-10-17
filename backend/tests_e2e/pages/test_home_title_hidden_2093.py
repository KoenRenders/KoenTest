"""E2E: the home page's title is its one h1 and is not drawn; the band is what a visitor sees first (#2093).

In a browser, because "not visible" is what the eye gets: the template carries the
kit's `sr-only`, and only the cascade says it is clipped to a pixel.

Broken on purpose (17 October 2026): the template drawing the title again for the home
page → the h1 measured 1 140 x 36 px (or 40 px high on a phone) and the first visible
block moved below it.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, pagina_klaar  # noqa: E402

_MEASURE = """() => {
  const h1s = [...document.querySelectorAll('#main h1')];
  const box = h1s.length ? h1s[0].getBoundingClientRect() : null;
  const page = document.querySelector('#main .doc-page');
  const first = [...page.children].find(el => el.tagName !== 'H1' && el.getBoundingClientRect().height > 8);
  return {h1: h1s.length, text: h1s.length ? h1s[0].textContent.trim() : '',
          w: box && box.width, h: box && box.height,
          firstTop: first ? first.getBoundingClientRect().top - page.getBoundingClientRect().top : null,
          firstText: first ? first.innerText.trim().slice(0, 80) : '',
          wide: [document.documentElement.scrollWidth, innerWidth]};
}"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


@pytest.mark.parametrize("width", [390, 1280])
def test_the_home_title_is_one_h1_that_takes_no_room(browser, width):
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    try:
        page.goto("/")
        pagina_klaar(page)
        measured = page.evaluate(_MEASURE)
        assert measured["h1"] == 1, f"the home page must have one h1: {measured}"
        assert measured["text"], "the h1 is empty"
        assert measured["w"] <= 1 and measured["h"] <= 1, f"the title is drawn: {measured}"
        assert measured["firstTop"] is not None and measured["firstTop"] < 24, (
            f"the first visible block starts below something: {measured}"
        )
        assert measured["wide"][0] <= measured["wide"][1] + 1, f"sideways scroll: {measured}"
    finally:
        page.close()
