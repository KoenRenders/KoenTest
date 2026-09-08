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


# ── #762: de knop keert terug naar de microfoon ──────────────────────────────

def test_de_microfoonknop_keert_terug_na_stoppen(page):
    """Gemeld: na het stoppen bleef de knop leeg (microfoon → vierkant → niets).

    **Niet gereproduceerd** — met een nagebootst native pad gaat de knop netjes heen
    en terug, op `/raakje` én in de widget. Deze test legt dat vast, zodat de melding
    niet stil terug kan komen; `stt.js` leest de iconen sinds #762 bij elke wissel
    opnieuw uit in plaats van ze bij het laden vast te leggen.

    Het native pad wordt nagebootst: headless Chromium heeft geen echte
    `SpeechRecognition`, en dát is het pad dat een gebruiker in Chrome neemt. Zonder
    die nabootsing zou deze test een ander pad toetsen dan de melding beschrijft.
    """
    page.add_init_script("""
        window.SpeechRecognition = function () {
          var self = this;
          this.start = function () {};
          this.stop = function () { if (self.onend) self.onend(); };
        };
    """)
    page.goto("/raakje")
    page.wait_for_selector("[data-stt-target]", timeout=5000)
    knop = page.locator("[data-stt-target]").first

    def inhoud():
        return knop.inner_html().strip()

    rust = inhoud()
    assert rust, "de knop is bij het laden al leeg"

    knop.click()
    page.wait_for_timeout(300)
    opnemen = inhoud()
    assert opnemen and opnemen != rust, "de knop toont geen andere stand tijdens opnemen"

    knop.click()
    page.wait_for_timeout(300)
    assert inhoud() == rust, (
        "de knop keert niet terug naar de microfoon — ze blijft leeg of op het "
        "vierkantje staan (#762)")
