"""E2E #1229 — de e-mailrij: geen herhaald label, alles op één lijn.

Twee meldingen van Koen met **één** oorzaak. Het label *E-mailadres* stond op
elke rij terwijl de kop er al *E-mailadressen* boven zet — bij twee adressen
staat het woord drie keer op één blok. En de badge *hoofdadres* stond hoger dan
het veld en de knoppen ernaast.

Dat tweede volgde uit het eerste: de rij was `items-end` omdat de eerste kolom
een label bóven het veld droeg, en bodem-uitlijning was toen de enige manier om
het veld gelijk te krijgen met de knoppen. Een badge is lager dan een
invoerveld en heeft eigen binnenmarge, dus die kwam hoger. Zonder label kan de
rij op het midden uitlijnen en staat alles vanzelf gelijk.

**Geen tolerantie in de uitlijningstest.** Bij #1197 bleek dat "binnen een pixel
of twee" een zichtbaar scheve knop groen laat staan. De middens moeten gelijk
zijn, punt.

**En de toegankelijke naam is de helft die het makkelijkst sneuvelt.** Een label
weghalen is één regel; een veld zonder naam is onbruikbaar met een schermlezer.
Drie velden die alle drie "E-mailadres" heten zijn dat trouwens ook — vandaar
het nummer.
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie  # noqa: E402


@pytest.fixture(scope="module")
def kaart():
    """Een ledenkaart in bewerkmodus, met twee e-mailadressen."""
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE, viewport={"width": 1440, "height": 900})
        login_met_sessie(page, make_session_value(email))
        page.goto("/admin/leden")
        page.goto(page.locator('a[href^="/admin/leden/gezin/"]').first.get_attribute("href"))
        page.get_by_role("button", name="Bewerken").first.click()
        page.get_by_role("button", name="+ E-mailadres").first.click()
        page.locator("[data-email-rij]").first.wait_for(state="visible", timeout=5_000)
        yield page
        browser.close()


def test_het_label_staat_niet_op_elke_rij(kaart):
    """De kop zegt het één keer; de rijen herhalen het niet.

    Tegenproef: `ui.label(...)` terug in de rij → het woord staat er dan per rij
    bij en deze test telt er meer dan één.
    """
    zichtbaar = kaart.evaluate("""() => {
      const blok = document.querySelector('[data-email-rij]').closest('div').parentElement;
      return [...blok.querySelectorAll('label')]
        .filter(l => l.offsetParent !== null)
        .map(l => l.textContent.trim());
    }""")
    assert zichtbaar.count("E-mailadres") == 0, (
        f"het label staat nog zichtbaar op de rijen: {zichtbaar}")


def test_elk_veld_houdt_een_eigen_toegankelijke_naam(kaart):
    """Zonder naam is het veld onbruikbaar met een schermlezer, en met drie keer
    dezelfde naam ook.

    Tegenproef: het `aria_label` weghalen → de eerste assertie valt om. Het
    nummer weghalen → de tweede, want dan heten ze alle drie hetzelfde.
    """
    namen = kaart.evaluate("""() => [...document.querySelectorAll('[data-email-rij] input')]
        .map(i => i.getAttribute('aria-label'))""")

    assert namen and all(namen), f"een veld zonder toegankelijke naam: {namen}"
    assert len(set(namen)) == len(namen), (
        f"twee velden dragen dezelfde naam, dus ze zijn niet uit elkaar te "
        f"houden: {namen}")


def test_veld_badge_en_knoppen_staan_op_een_lijn(kaart):
    """De melding van Koen, gemeten op het MIDDEN en zonder tolerantie.

    Bij #1197 is gebleken dat "binnen een pixel of twee" een zichtbaar scheve
    knop groen laat staan; die les hoort hier niet opnieuw geleerd te worden.

    Tegenproef: `items-center` terug op `items-end` → de badge komt hoger te
    staan en de middens lopen uiteen.
    """
    middens = kaart.evaluate("""() => {
      const rij = [...document.querySelectorAll('[data-email-rij]')]
        .find(r => r.querySelector('span.rounded-full'));
      if (!rij) return null;
      return [...rij.children].map(k => {
        const r = k.getBoundingClientRect();
        return {wat: k.tagName + '.' + (k.className || '').split(' ')[0],
                midden: Math.round(r.top + r.height / 2)};
      });
    }""")
    assert middens, "geen rij met een hoofdadres-badge gevonden"
    assert len(middens) >= 2, f"te weinig elementen om uit te lijnen: {middens}"

    waarden = {m["midden"] for m in middens}
    assert len(waarden) == 1, (
        f"de elementen van de rij staan niet op één lijn: {middens}")
