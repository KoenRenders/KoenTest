"""E2E: "Word lid" prefills partner, then child, as people are added (#1321).

The relation of a new person is prefilled by `membership.default_relation`, from
the relations already on the form. Walked in the browser at 390 and 1280 px:

- "+ Gezinslid toevoegen" twice: person 2 shows "Partner", person 3 "(meerderjarig)
  kind";
- person 2 changed to child by hand, then a person added: that one is the
  partner, because there is none yet;
- the choice stays editable, and nothing sticks out of the screen.

Proven red against master `54bc8681` (29 September 2026): a server built from it
left person 3 on the browser's first option, "Partner".
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_stil, pagina_klaar  # noqa: E402

_STATE = """() => ({
  relations: [...document.querySelectorAll('select[name$="_relation_type"]')]
    .map(s => s.value),
  labels: [...document.querySelectorAll('select[name$="_relation_type"]')]
    .map(s => s.options[s.selectedIndex].text.trim()),
  doc: document.documentElement.scrollWidth, vw: innerWidth,
})"""


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _add(page) -> None:
    page.get_by_role("button", name="+ Gezinslid toevoegen").click()
    htmx_stil(page)


@pytest.mark.parametrize("width", [390, 1280])
def test_partner_then_child(browser, width):
    context = browser.new_context(base_url=BASE, viewport={"width": width, "height": 900})
    page = context.new_page()
    try:
        page.goto("/lid-worden")
        pagina_klaar(page)
        _add(page)
        _add(page)
        state = page.evaluate(_STATE)
        assert state["relations"] == ["PARTNER", "KIND"], f"@{width}: {state}"
        assert state["doc"] <= state["vw"], state

        # By hand: person 2 is a child after all; the next person is the partner.
        page.select_option('select[name="m1_relation_type"]', "KIND")
        _add(page)
        state = page.evaluate(_STATE)
        assert state["relations"] == ["KIND", "KIND", "PARTNER"], f"@{width}: {state}"
    finally:
        context.close()
