"""E2E #1171/#1172 — de aantal-teller, gemeten in een echte browser.

Twee dingen zijn alleen hier te zien, en het zijn precies de twee waar dit
issue om draait.

**De keten van klik tot nieuw totaal.** Een waarde die JavaScript zet stuurt géén
`change`-gebeurtenis; de teller vuurt er daarom zelf een af. Gebeurt dat niet, dan
klimt het cijfer wél en blijft *Totaal: €0,00* staan — de bezoeker bevestigt dan
een bedrag dat niet op het scherm klopt. Een markuptest ziet die regel staan; pas
een browser ziet of htmx erop reageert en of het server-side herrekende bedrag
echt verandert. `tests/test_inschrijf_teller.py` doet de goedkope helft.

**Het aanraakvlak.** 44 px (#804) is een MAAT en geen klassenaam. `h-11 w-11`
kan kloppen terwijl een ouder in de flexrij de knop indrukt, en dat zie je alleen
aan `getBoundingClientRect`.

Kapotgemaakt om te controleren dat deze test rood kan worden: de regel
`dispatchEvent(new Event('change'…))` uit de `stepper`-macro gehaald. Gemeten
resultaat: het aantal klimt netjes naar 2 en het totaal blijft op *€ 10,00* —
de openingsprijs van één stuk. De aantal-assertie blijft dus groen en alleen de
totaal-assertie valt om, met de gemeten waarde in de melding. Dat is precies het
verschil dat dit bestand moet kunnen zien; "het getal klimt" bewijst niets.

Gemeten op telefoonbreedte (390 px): dat is de stand waar het probleem zich
voordeed, en 80% van het publieke bezoek.
"""
import os
import sys

import pytest
from playwright.sync_api import TimeoutError as PlaywrightTimeout
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE  # noqa: E402

MIN_RAAKVLAK = 44


def _ontbreekt(reden: str) -> None:
    if os.environ.get("E2E_SEEDED") == "1":
        pytest.fail(f"e2e-seed geladen maar: {reden}")
    pytest.skip(reden)


def _open_het_formulier(page):
    """De inschrijfmodal van de geseede activiteit met één betalend product."""
    page.goto("/activiteiten")
    page.wait_for_selector("h2")
    knop = page.get_by_role("button", name="Inschrijven").first
    if knop.count() == 0:
        _ontbreekt("geen activiteit met een open inschrijving op /activiteiten")
    knop.click()
    page.wait_for_selector("input[name^='product_']", timeout=10_000)


def _stand(page) -> dict:
    return page.evaluate("""() => {
      const veld = document.querySelector("input[name^='product_']");
      const teller = veld.closest('div');
      const knoppen = [...teller.querySelectorAll('button')].map(b => {
        const r = b.getBoundingClientRect();
        return { label: b.getAttribute('aria-label'),
                 breedte: Math.round(r.width), hoogte: Math.round(r.height) };
      });
      const totaal = document.querySelector("[id^='totaal-']");
      return { aantal: veld.value, knoppen,
               totaal: (totaal ? totaal.innerText : '').replace(/\\s+/g, ' ').trim() };
    }""")


def test_de_teller_verhoogt_het_aantal_en_het_totaal_beweegt_mee():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
        _open_het_formulier(page)

        # #1172: één product, dus het formulier opent op 1 met de prijs erbij.
        begin = _stand(page)
        assert begin["aantal"] == "1", (
            f"één product hoort op 1 te openen, gekregen: {begin['aantal']!r}")
        assert "10" in begin["totaal"], (
            f"het totaal toont de prijs niet bij het openen: {begin['totaal']!r}")

        # #1171, punt 4: een MAAT, geen klassenaam.
        assert len(begin["knoppen"]) == 2, (
            f"twee tellerknoppen verwacht: {begin['knoppen']}")
        for knop in begin["knoppen"]:
            assert knop["label"], f"een tellerknop zonder aria-label: {knop}"
            assert knop["breedte"] >= MIN_RAAKVLAK and knop["hoogte"] >= MIN_RAAKVLAK, (
                f"knop {knop['label']!r} meet {knop['breedte']}×{knop['hoogte']}px, "
                f"minimaal {MIN_RAAKVLAK}px (#804)")

        # #1171, punt 1 — de belangrijkste. Het getal klimt ÉN het totaal volgt.
        page.get_by_role("button", name="Eén meer").first.click()
        page.wait_for_function(
            "() => document.querySelector(\"input[name^='product_']\").value === '2'",
            timeout=5_000)
        # Wachten mag mislukken: blijft het totaal staan, dan is dát de bevinding
        # en hoort de assertie hieronder ze te melden. Een kale `wait_for_function`
        # zou hier een Playwright-timeout opleveren, en die zegt niet wat er stuk
        # is — gemeten bij de tegenproef, en daarom staat deze try eromheen.
        try:
            page.wait_for_function(
                """(vorig) => {
                     const t = document.querySelector("[id^='totaal-']");
                     return t && t.innerText.replace(/\\s+/g, ' ').trim() !== vorig;
                   }""",
                arg=begin["totaal"], timeout=8_000)
        except PlaywrightTimeout:
            pass

        na = _stand(page)
        assert na["aantal"] == "2"
        assert "20" in na["totaal"], (
            f"het totaal bewoog niet mee naar twee stuks: {na['totaal']!r} — de "
            "teller vuurt waarschijnlijk geen change af, en dan bevestigt de "
            "bezoeker een bedrag dat niet op het scherm staat")

        browser.close()


def test_de_teller_stopt_op_nul():
    """`−` gaat niet onder `min`. Zonder deze grens zou het veld een negatief
    aantal kunnen dragen dat de server daarna moet afwijzen."""
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
        _open_het_formulier(page)

        minder = page.get_by_role("button", name="Eén minder").first
        for _ in range(3):
            minder.click()
        page.wait_for_function(
            "() => document.querySelector(\"input[name^='product_']\").value === '0'",
            timeout=5_000)

        assert _stand(page)["aantal"] == "0", "de teller zakte onder nul"
        browser.close()
