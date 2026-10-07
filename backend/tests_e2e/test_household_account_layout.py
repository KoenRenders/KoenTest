"""E2E: Mijn gezin and the renewal page stand in the account layout (CR-22,
#1723) — the menu of the account pages on the left, as on Mijn gegevens.

- at 1440, 768 and 390 px the menu's box and the content's box on Mijn gezin
  (reading and editing) and on the renewal page equal those on Mijn gegevens;
  "Mijn gezin" is the marked item; nothing is wider than the window; in the
  edit mode the action bar and every field stand inside the content column;
- a member walks from "Mijn <site>" to Mijn gezin and on to Mijn gegevens
  through the menu on the left, without the header's menu.

On master the two pages have no `[data-account-page]`: the first test fails at
"no account layout", the walk at the menu on Mijn gezin.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

HOUSEHOLD = "/leden/gezin"


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _member(browser, width: int, height: int):
    from app.domains.auth.api import make_session_value
    from seed_e2e import MARKER_EMAIL

    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": height})
    login_met_sessie(page, make_session_value(MARKER_EMAIL), BASE)
    return page


LAYOUT = """() => { const q = s => document.querySelector(s);
  const box = e => { const b = e.getBoundingClientRect(); return [Math.round(b.left), Math.round(b.width)]; };
  const layout = q('[data-account-page]');
  if (!layout) return null;
  const menu = q('[data-account-page-menu]'), content = q('[data-account-content]'), bar = q('[data-action-bar]');
  const shown = menu.checkVisibility();
  const inside = e => { const b = e.getBoundingClientRect(), c = content.getBoundingClientRect();
    return b.left >= c.left - 0.5 && b.right <= c.right + 0.5; };
  const fields = [...content.querySelectorAll('input:not([type=hidden]), select, textarea')].filter(e => e.checkVisibility());
  return {menu: shown ? box(menu) : null, content: box(content),
          current: [...menu.querySelectorAll('a[aria-current="page"]')].map(a => a.getAttribute('href')),
          menus: document.querySelectorAll('[data-account-page-menu]').length,
          form: box(q('[data-public-form-page]')),
          bar: bar && bar.checkVisibility() ? inside(bar) : null,
          fields: fields.length, outside: fields.filter(e => !inside(e)).length,
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


def _measure(page, path: str) -> dict:
    page.goto(path)
    pagina_klaar(page)
    found = page.evaluate(LAYOUT)
    assert found is not None, f"{path}: no account layout on the page"
    return found


@pytest.mark.parametrize(
    ("width", "height", "menu"), [(390, 844, False), (768, 1024, True), (1440, 900, True)]
)
def test_the_household_pages_stand_in_the_account_layout(browser, width, height, menu):
    page = _member(browser, width, height)
    details = _measure(page, "/mijn/gegevens")
    assert (details["menu"] is not None) is menu, details
    for path, edit in (
        (HOUSEHOLD, False),
        (HOUSEHOLD + "?bewerken=1", True),
        (HOUSEHOLD + "/vernieuwen", None),
    ):
        found = _measure(page, path)
        if path.endswith("/vernieuwen") and not page.url.endswith("/vernieuwen"):
            # A renewal that cannot start lands on Mijn gezin: measured above.
            continue
        print("MEASURE household layout", width, path, found)
        assert found["menu"] == details["menu"], (
            f"{path}: the menu's box differs from Mijn gegevens'"
        )
        assert found["content"] == details["content"], (
            f"{path}: the content's box differs from Mijn gegevens'"
        )
        assert found["menus"] == 1 and found["current"] == [HOUSEHOLD], found
        assert found["form"][1] == found["content"][1] and found["form"][1] <= 768, found
        assert found["page"][0] == found["page"][1], f"{path}: wider than the window"
        if edit:
            # On a phone the bar is the window's, edge to edge, as on every form page.
            assert found["bar"] is menu, f"{path}: the action bar is not inside the content column"
            assert found["fields"] > 8 and found["outside"] == 0, found
        elif edit is False:
            assert found["bar"] is None
    page.close()


def test_from_the_landing_page_to_mijn_gezin_and_on_through_the_menu_on_the_left(browser):
    page = _member(browser, 1440, 900)
    page.goto("/mijn")
    pagina_klaar(page)
    page.locator(f'[data-account-page-menu] a[href$="{HOUSEHOLD}"]').click()
    page.wait_for_url(f"**{HOUSEHOLD}")
    pagina_klaar(page)
    assert page.locator("#main h1").inner_text().strip() == "Mijn gezin"
    menu = page.locator("[data-account-page-menu]")
    assert menu.is_visible(), "Mijn gezin has no menu on the left"
    assert menu.locator('a[aria-current="page"]').get_attribute("href").endswith(HOUSEHOLD)
    menu.locator('a[href$="/mijn/gegevens"]').click()
    page.wait_for_url("**/mijn/gegevens")
    pagina_klaar(page)
    assert page.locator("#main h1").inner_text().strip() == "Mijn gegevens"
    page.close()
