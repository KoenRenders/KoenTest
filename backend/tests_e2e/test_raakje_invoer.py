"""E2E: de vraagvelden van Raakje groeien mee en Enter verstuurt (#570).

Het was een `<input>` van één regel. Bij een langere vraag zag je nog een stukje van
wat je typte, en de rest verdween links uit beeld — precies bij het soort vraag
waarvoor de bot bedoeld is.

**Toetsaanslag-gedrag is browsergedrag**, dus dit hoort hier en niet in een
servertest. En de tweede test is er omdat de eerste alleen niets bewijst: zonder
Shift+Enter zou "Enter verstuurt" ook groen staan wanneer Enter helemaal niets doet
en de vorm gewoon leeg blijft.

Getoetst op `/raakje` en niet op de widget: die staat achter `CHAT_ENABLED`, dat in
CI uit staat. Beide schermen dragen dezelfde textarea en hetzelfde toetsgedrag.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: de
`x-on:keydown.enter`-handler weggehaald → de eerste test valt om (het veld houdt een
nieuwe regel in plaats van te versturen); de `x-on:input`-handler weggehaald → de
groeitest valt om.
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE  # noqa: E402


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        p = browser.new_page(base_url=BASE)
        yield p
        browser.close()


def _veld(page):
    page.goto("/raakje")
    page.wait_for_selector("#raakje-vraag", timeout=5000)
    return page.locator("#raakje-vraag")


def test_het_veld_groeit_mee_met_een_lange_vraag(page):
    veld = _veld(page)
    hoogte_leeg = veld.bounding_box()["height"]

    veld.fill("Ik heb een vrij lange vraag over het lidmaatschap. " * 4)
    page.wait_for_timeout(200)

    hoogte_vol = veld.bounding_box()["height"]
    assert hoogte_vol > hoogte_leeg, (
        "het veld groeit niet mee — een langere vraag verdwijnt dan uit beeld")
    assert hoogte_vol <= 130, (
        f"het veld groeit ongeremd door ({hoogte_vol}px); boven ~120px hoort het te "
        "scrollen")


def test_shift_enter_geeft_een_nieuwe_regel(page):
    """De tegenproef bij "Enter verstuurt". Zonder haar bewijst die niets."""
    veld = _veld(page)
    veld.click()
    page.keyboard.type("eerste regel")
    page.keyboard.press("Shift+Enter")
    page.keyboard.type("tweede regel")

    assert "\n" in veld.input_value(), "Shift+Enter geeft geen nieuwe regel"
    assert page.url.endswith("/raakje"), "het formulier is toch verstuurd"


def test_enter_verstuurt(page):
    veld = _veld(page)
    veld.click()
    page.keyboard.type("Wanneer is de volgende activiteit?")
    page.keyboard.press("Enter")
    page.wait_for_timeout(1200)

    assert "\n" not in veld.input_value(), (
        "Enter zette een nieuwe regel in plaats van te versturen")
    assert page.locator("#raakje-gesprek").inner_text().strip() != "", (
        "er is niets verstuurd")
