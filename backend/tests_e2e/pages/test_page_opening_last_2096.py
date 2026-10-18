"""E2E: the page screen puts the text before the opening (#2096).

The opening's ten fields stood between Gegevens and the text, so the editor began
below the first screen on a phone. They are now the kit's closed `rare_settings`
after Inhoud. Read from the rendered page at 390 and 1 280 px: the editor's top is
above the opening section's top, the opening is closed (its fields take no room),
its summary line is the section's height, and the page is no wider than the window.
A refusal about the hero opens it again, so the author sees the fields at fault.

Broken on purpose (18 October 2026): the opening a `section` between Gegevens and
Inhoud again (master's template) → all three red: no closed opening to measure
(a TypeError in the measurement) and no section to open on a refusal.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.pages.test_cards_1770 import _new_page, _open  # noqa: E402

SHOTS = "/scratch/shots_2096"
_MEASURE = """() => {
  const top = el => Math.round(el.getBoundingClientRect().top + scrollY);
  const rare = document.querySelector('details[data-rare-settings]');
  const editor = document.querySelector('#cp-document');
  const field = rare.querySelector('[name=hero_tone]');
  return {
    'editor top': top(editor),
    'opening top': top(rare),
    'opening height': Math.round(rare.getBoundingClientRect().height),
    'open': rare.open,
    'summary': rare.querySelector('[data-rare-summary]').textContent.trim(),
    'field visible': field.checkVisibility(),
    'sections': [...document.querySelectorAll('#cp-form > [data-form-section] > h2, #cp-form > details > summary > span > span:first-child')]
      .map(e => e.textContent.trim()),
    'page wider than the window by': document.documentElement.scrollWidth - innerWidth,
  };
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


@pytest.mark.parametrize("width", [390, 1280])
def test_the_editor_stands_above_the_closed_opening(setup, width):
    browser, session = setup
    page_id, _slug = _new_page(f"Opening {width}")
    page = _open(browser, session, page_id, width)
    try:
        seen = page.evaluate(_MEASURE)
        print("MEASURE", width, seen)
        if os.path.isdir("/scratch"):
            os.makedirs(SHOTS, exist_ok=True)
            page.screenshot(path=f"{SHOTS}/{width}.png", full_page=True)
        assert seen["sections"] == ["Gegevens", "Inhoud", "Opening van de pagina"], seen
        assert seen["editor top"] < seen["opening top"], (
            f"the opening stands above the text: {seen}"
        )
        assert not seen["open"] and not seen["field visible"], f"the opening is open: {seen}"
        assert seen["opening height"] < 80, f"the closed opening is more than its line: {seen}"
        assert seen["summary"] == "Titelregel", seen
        assert seen["page wider than the window by"] <= 0, seen
    finally:
        page.close()


def test_a_hero_refusal_opens_the_opening(setup):
    browser, session = setup
    page_id, _slug = _new_page("Opening geweigerd")
    page = _open(browser, session, page_id, 390)
    try:
        page.locator("details[data-rare-settings] > summary").click()
        page.select_option("[name=opening]", "hero")
        page.fill("[name=hero_b1_label]", "Contact")
        page.locator("details[data-rare-settings] > summary").click()
        assert not page.evaluate("document.querySelector('details[data-rare-settings]').open")
        page.locator("[data-action-bar] button[data-form-save]").click()
        page.wait_for_selector("[data-error-banner], [role=alert]", timeout=10000)
        opened = page.evaluate("document.querySelector('details[data-rare-settings]').open")
        assert opened, "the refusal names the hero's fields, but the section stayed closed"
    finally:
        page.close()
