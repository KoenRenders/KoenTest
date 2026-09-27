"""E2E #1238: een opname draagt de omgevingsbanner niet, een gewone weergave wél.

`tests_e2e/screenshots.py` is gereedschap en geen test — pytest verzamelt het niet, dus
niets bewijst dat de tool de vlag werkelijk meestuurt. De pytest-kant
(`tests/test_schermafdruk_zonder_omgevingsbanner.py`) toetst de beslissing van de schil
met een zelf gezette header; dat blijft groen als de tool die header nooit verzendt.

Deze test sluit dat gat: hij opent een browsercontext met **de instellingen van de tool
zelf** (`screenshots.context_opties()`) en meet in de pagina of de balk er staat. Typt
hij de headernaam na, dan meet hij zijn eigen kopie en overleeft hij een tool die de
vlag kwijtraakt.

De tweede test is de tegenproef die ertoe doet: dezelfde pagina, dezelfde omgeving, een
gewone context — daar hoort de waarschuwing te blijven staan. Zonder haar kan de
reparatie de banner overal gesloopt hebben.

Rood gemaakt om te toetsen dát ze kunnen falen, elk apart gemeten: met
`extra_http_headers` uit `context_opties()` gehaald faalt de eerste (1 failed, 1 passed);
met `_is_screenshot` op onvoorwaardelijk `True` — de banner overal weg — faalt de tweede
(1 failed, 1 passed).
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE  # noqa: E402
from tests_e2e.screenshots import context_opties  # noqa: E402

# De tekst uit `ui.env_banner` (_macros.html) — de balk zoals een bezoeker hem leest.
BANNER = "testomgeving (geen productie)"

TELEFOON = {"width": 390, "height": 844}


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _tekst_van_de_homepage(browser, **context_kwargs) -> str:
    context = browser.new_context(base_url=BASE, viewport=TELEFOON, **context_kwargs)
    try:
        page = context.new_page()
        page.goto("/")
        page.wait_for_selector("main", timeout=5000)
        return page.locator("body").inner_text()
    finally:
        context.close()


def test_een_opname_draagt_de_balk_niet(browser):
    """Met de instellingen van de tool — niet met een nagetypte header."""
    opties = context_opties()
    assert opties.get("extra_http_headers"), (
        "de tool stuurt geen enkele header mee; de vlag uit #1238 is verdwenen")
    assert BANNER not in _tekst_van_de_homepage(browser, **opties)


def test_een_gewone_bezoeker_op_dezelfde_omgeving_ziet_de_balk_wel(browser):
    """De tegenproef: de waarschuwing hoort te blijven waar ze hoort."""
    assert BANNER in _tekst_van_de_homepage(browser)
