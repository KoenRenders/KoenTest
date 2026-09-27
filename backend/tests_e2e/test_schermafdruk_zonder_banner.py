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


# De zwevende chatbel (#1241). Op haar `aria-label` en niet op de emoji: het label is
# wat een schermlezer voorleest en wijzigt niet mee met een ander icoon.
CHATBEL = "Raakje"


def _homepage(browser, **context_kwargs):
    context = browser.new_context(base_url=BASE, viewport=TELEFOON, **context_kwargs)
    try:
        page = context.new_page()
        page.goto("/")
        page.wait_for_selector("main", timeout=5000)
        yield page
    finally:
        context.close()


def _tekst_van_de_homepage(browser, **context_kwargs) -> str:
    for page in _homepage(browser, **context_kwargs):
        return page.locator("body").inner_text()
    raise AssertionError("de homepagina leverde geen pagina op")


def _aantal_chatbellen(browser, **context_kwargs) -> int:
    for page in _homepage(browser, **context_kwargs):
        return page.get_by_role("button", name=CHATBEL).count()
    raise AssertionError("de homepagina leverde geen pagina op")


def test_een_opname_draagt_de_balk_niet(browser):
    """Met de instellingen van de tool — niet met een nagetypte header."""
    opties = context_opties()
    assert opties.get("extra_http_headers"), (
        "de tool stuurt geen enkele header mee; de vlag uit #1238 is verdwenen")
    assert BANNER not in _tekst_van_de_homepage(browser, **opties)


def test_een_gewone_bezoeker_op_dezelfde_omgeving_ziet_de_balk_wel(browser):
    """De tegenproef: de waarschuwing hoort te blijven waar ze hoort."""
    assert BANNER in _tekst_van_de_homepage(browser)


def test_een_opname_draagt_de_chatbel_niet(browser):
    """#1241: de zwevende chatbel dekt op een volledige-paginaopname een bediening af.

    Ze staat `position: fixed`, dus in zo'n opname landt ze op haar viewportpositie
    MIDDEN in de pagina in plaats van rechtsonder — op de reeks van #1238 lag ze over
    de knop "Bewerken" van een gezinslid en over het veld "Telefoon". Dezelfde soort
    afwijking als de omgevingsbanner, en daarom dezelfde vlag en geen tweede
    mechanisme.
    """
    assert _aantal_chatbellen(browser, **context_opties()) == 0


def test_een_gewone_bezoeker_ziet_de_chatbel_wel(browser):
    """De tegenproef die ertoe doet: Raakje is een functie die Koen bewust op het
    publieke deel gezet heeft, dus ze mag niet per ongeluk overal verdwijnen."""
    assert _aantal_chatbellen(browser) == 1
