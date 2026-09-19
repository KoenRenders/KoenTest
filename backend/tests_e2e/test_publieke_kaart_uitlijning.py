"""E2E: de acties van een activiteitkaart liggen op de inhoudsrand (F32, #913).

Golf 11, beslist door Koen op 19 september 2026. Op een breed scherm stonden de
knoppen onder de datumtegel, los van titel en gegevens — één activiteit las als
twee blokken. Nu staan ze in de inhoudskolom, met dezelfde linkerkant als de
titel. Op een telefoon geldt het omgekeerde bewust: daar nemen de acties de
volle kaartbreedte (anders wrappen de twee knoppen), dus daar beginnen ze wél
links van de titel.

Dit is de meting bij de bronassert in tests/test_golf11_home.py — een
markuptest kan de kolomstructuur beloven, alleen een gerenderde kaart bewijst
de gelijke linkerkant.

Kapotgemaakt om te controleren dat deze test rood kan worden: het actieblok
terug buiten de inhoudskolom gezet (de twee sluittags weer vóór het blok) → de
desktoptest valt om op de linkerkant; de `-ml-[60px]` weggehaald → de mobiele
tegenproef valt om.
"""
import os
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE  # noqa: E402

def _meet(page):
    return page.evaluate("""() => {
      const titel = document.querySelector('h2 span, h2 a');
      const kaart = titel.closest('div[id]');
      const knop = kaart.querySelector('button');
      return {
        titel: Math.round(titel.getBoundingClientRect().left),
        knop: Math.round(knop.getBoundingClientRect().left),
      };
    }""")


def test_desktop_acties_op_de_inhoudsrand_mobiel_volle_breedte():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
        page.goto("/activiteiten")
        page.wait_for_selector("h2 span, h2 a")

        d = _meet(page)
        assert d["knop"] == d["titel"], (
            f"desktop: de knop begint op {d['knop']}px, de titel op {d['titel']}px — "
            "de acties horen op de inhoudsrand")

        page.set_viewport_size({"width": 390, "height": 844})
        m = _meet(page)
        assert m["knop"] < m["titel"], (
            f"mobiel: de knop ({m['knop']}px) hoort de volle kaartbreedte te nemen, "
            f"links van de titelinsprong ({m['titel']}px)")
        browser.close()
