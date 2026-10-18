"""E2E: on a phone the list header's button stands under the title (#2126).

Since #2106 the create button of a list header carries its glyph and is 22 px wider:
beside the title at 390 px it cut "Gebruikers" and "Formulieren". On a phone the title
takes the whole row now and the buttons stand under it; from `md` the header is one
row as before. Measured on the rendered DOM: the title's scroll width equals its
client width (it is not cut) and the first button's top lies below the title's
bottom at 390 px; at 1 280 px the button shares the title's row.

Broken on purpose (18 October 2026), put back by the reverse edit: `basis-full`
taken off the title of `page_header` → "Gebruikers" at 390 px red (the title is cut and
the button beside it).
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

#: The four lists of the finding, and the busiest header: figures and a button.
LISTS = [
    "/admin/gebruikers",
    "/admin/formulieren",
    "/admin/nieuwsbrieven",
    "/admin/vergaderingen",
    "/admin/leden",
]

_HEAD = """() => {
  const h1 = document.querySelector('main h1');
  const title = h1.getBoundingClientRect();
  const first = [...document.querySelectorAll('[data-header-actions] > *, [data-list-primary] > *')]
    .filter(el => el.offsetParent)[0];
  const button = first ? first.getBoundingClientRect() : null;
  return {text: h1.innerText.trim(), cut: h1.scrollWidth > h1.clientWidth,
          buttonTop: button ? Math.round(button.top) : null, titleBottom: Math.round(title.bottom),
          titleTop: Math.round(title.top), sideways: document.documentElement.scrollWidth > innerWidth};
}"""


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


@pytest.mark.parametrize("path", LISTS)
def test_the_button_stands_under_the_title_on_a_phone(setup, path):
    browser, session = setup
    page = browser.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
    try:
        login_met_sessie(page, session)
        page.goto(path)
        pagina_klaar(page)
        m = page.evaluate(_HEAD)
        print("MEASURE list head 390", path, m)
        assert m["buttonTop"] is not None, f"{path}: no header button found"
        assert not m["cut"], f"{path}: the title is cut: {m}"
        assert m["buttonTop"] >= m["titleBottom"], f"{path}: the button is not under the title: {m}"
        assert not m["sideways"], f"{path}: the page scrolls sideways"
    finally:
        page.close()


@pytest.mark.parametrize("path", LISTS)
def test_title_and_button_share_one_row_on_a_wide_screen(setup, path):
    browser, session = setup
    page = browser.new_page(base_url=BASE, viewport={"width": 1280, "height": 900})
    try:
        login_met_sessie(page, session)
        page.goto(path)
        pagina_klaar(page)
        m = page.evaluate(_HEAD)
        print("MEASURE list head 1280", path, m)
        assert m["buttonTop"] is not None, f"{path}: no header button found"
        assert not m["cut"], f"{path}: the title is cut: {m}"
        assert m["buttonTop"] < m["titleBottom"], f"{path}: the button left the title's row: {m}"
    finally:
        page.close()
