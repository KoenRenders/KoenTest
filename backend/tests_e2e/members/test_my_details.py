"""E2E: Mijn gegevens in the browser (CR-22 S6a, #1710; R16, R17).

- the page stands in the account layout: on a desktop the menu on the left with
  "Mijn gegevens" marked, on a phone no menu on the page; nothing wider than the
  window, the fields inside their card;
- "Bewerken" opens the edit mode, ONE "Opslaan" writes, and the page comes back
  in read mode saying so — the same round as Mijn gezin;
- what is saved here stands in Mijn gezin.

The seeded member's first name is changed and put back.

On master `d45633ff` there is no route `/mijn/gegevens`.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402


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


PAGE = """() => { const q = s => document.querySelector(s), r = e => e.getBoundingClientRect();
  const menu = q('[data-account-page-menu]'), card = q('[data-my-details]');
  const inputs = [...document.querySelectorAll('#gegevens-form input:not([type=hidden])')].filter(i => i.checkVisibility());
  return {menu: menu.checkVisibility(), current: [...menu.querySelectorAll('a[aria-current="page"]')].map(a => a.getAttribute('href')),
          title: q('#main h1').textContent.trim(), card: [Math.round(r(card).left), Math.round(r(card).width)],
          content: [Math.round(r(q('[data-account-content]')).left), Math.round(r(q('[data-account-content]')).width)],
          fields: inputs.map(i => i.getAttribute('name')),
          inside: inputs.every(i => r(i).left >= r(card).left && r(i).right <= r(card).right + 0.5),
          heights: inputs.map(i => Math.round(r(i).height)),
          action: q('[data-page-action] a') ? q('[data-page-action] a').textContent.trim() : null,
          bar: !!q('[data-action-bar]') && q('[data-action-bar]').checkVisibility(),
          page: [document.documentElement.scrollWidth, innerWidth]}; }"""


@pytest.mark.parametrize(("width", "height", "menu"), [(390, 844, False), (1440, 900, True)])
def test_the_page_stands_in_the_account_layout(browser, width, height, menu):
    page = _member(browser, width, height)
    page.goto("/mijn/gegevens")
    pagina_klaar(page)
    read = page.evaluate(PAGE)
    print("MEASURE my details read", width, read)
    assert read["title"] == "Mijn gegevens" and read["action"] == "Bewerken" and not read["bar"]
    assert read["menu"] is menu and read["current"] == ["/mijn/gegevens"], read
    assert read["card"][1] == read["content"][1] and read["card"][1] <= 768, read
    assert read["page"][0] == read["page"][1]
    page.goto("/mijn/gegevens?bewerken=1")
    pagina_klaar(page)
    edit = page.evaluate(PAGE)
    print("MEASURE my details edit", width, edit)
    own = [name.rsplit(".", 1)[-1] for name in edit["fields"] if name.startswith("h.")]
    assert own == ["first_name", "last_name", "mobile"], edit["fields"]
    assert any(name.startswith("e.") for name in edit["fields"]), "no e-mail field"
    assert edit["inside"] and edit["bar"] and edit["action"] is None, edit
    # A field is a finger high on a phone, a control high on a desktop.
    assert min(edit["heights"]) >= (44 if width == 390 else 40), edit["heights"]
    assert edit["page"][0] == edit["page"][1]
    page.close()


def test_one_save_writes_and_mijn_gezin_shows_it(browser):
    page = _member(browser, 390, 844)
    page.goto("/mijn/gegevens?bewerken=1")
    pagina_klaar(page)
    first = page.locator('#gegevens-form input[name$=".first_name"]')
    was = first.input_value()
    assert was, "the seeded member has no first name"
    try:
        first.fill("Meetnaam")
        page.locator(
            '[data-action-bar] button[type="submit"], [data-action-bar] button[form="gegevens-form"]'
        ).first.click()
        page.wait_for_function(
            "() => document.querySelector('[data-form-flow]').dataset.mode === 'read'"
        )
        pagina_klaar(page)
        assert page.url.endswith("/mijn/gegevens"), page.url
        assert "Meetnaam" in page.locator("[data-my-details]").inner_text()
        page.goto("/leden/gezin")
        pagina_klaar(page)
        assert "Meetnaam" in page.locator("[data-household-main]").inner_text()
    finally:
        page.goto("/mijn/gegevens?bewerken=1")
        pagina_klaar(page)
        page.locator('#gegevens-form input[name$=".first_name"]').fill(was)
        page.locator(
            '[data-action-bar] button[type="submit"], [data-action-bar] button[form="gegevens-form"]'
        ).first.click()
        page.wait_for_function(
            "() => document.querySelector('[data-form-flow]').dataset.mode === 'read'"
        )
        page.close()
