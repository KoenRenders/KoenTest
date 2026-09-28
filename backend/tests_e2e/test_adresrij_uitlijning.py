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
def browser():
    """Eén browser voor dit bestand.

    Eén `sync_playwright()` en niet twee: de synchrone API laat zich niet
    nesten, en twee fixtures die er elk een openen geven *"Sync API inside the
    asyncio loop"*. De twee schermbreedtes hieronder zijn dus twee PAGINA'S op
    dezelfde browser.
    """
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _kaart_in_bewerkmodus(browser, breedte: int):
    """Een ledenkaart in bewerkmodus met twee e-mailrijen, op deze breedte."""
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    page = browser.new_page(base_url=BASE, viewport={"width": breedte, "height": 900})
    login_met_sessie(page, make_session_value(email))
    page.goto("/admin/leden")
    page.goto(page.locator('a[href^="/admin/leden/gezin/"]').first.get_attribute("href"))
    page.get_by_role("button", name="Bewerken").first.click()
    page.locator("[data-email-rij]").first.wait_for(state="visible", timeout=5_000)
    aantal = page.locator("[data-email-rij]").count()
    page.get_by_role("button", name="+ E-mailadres").first.click()
    # Wachten op de TWEEDE rij en niet op de eerste: die bestond al, dus die
    # wachtvoorwaarde was meteen waar en de meting liep vóór de nieuwe rij er was.
    page.wait_for_function(
        "n => document.querySelectorAll('[data-email-rij]').length > n", arg=aantal, timeout=5_000
    )
    return page


@pytest.fixture(scope="module")
def kaart(browser):
    """Het beheerscherm op desktopbreedte — zo wordt het beoordeeld (CR-08)."""
    return _kaart_in_bewerkmodus(browser, 1440)


@pytest.fixture(scope="module")
def kaart_telefoon(browser):
    """Dezelfde kaart op 390 px.

    Een eigen breedte en niet de desktopfixture: op 1440 px past een rij op één
    regel, en dan meet de groeperingstest niets. Dat is precies wat er gebeurde
    toen ze de brede fixture leende — ze sloeg af met "geen enkele rij wrapt",
    en dat was terecht.
    """
    return _kaart_in_bewerkmodus(browser, 390)


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
        f"het label staat nog zichtbaar op de rijen: {zichtbaar}"
    )


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
        f"twee velden dragen dezelfde naam, dus ze zijn niet uit elkaar te houden: {namen}"
    )


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
    assert len(waarden) == 1, f"de elementen van de rij staan niet op één lijn: {middens}"


def test_twee_rijen_staan_verder_uit_elkaar_dan_hun_eigen_regels(kaart_telefoon):
    """Op telefoonbreedte wrapt een rij; dan moet de groepering kloppen.

    Veld boven, knoppen eronder — en als de afstand tússen twee rijen niet
    duidelijk groter is dan die binnen één rij, staat de rode *Verwijderen* van
    de ene rij vlak boven het VELD van de volgende. Dat is een verwijderactie bij
    het verkeerde adres, en op het GEZINSPORTAAL — dat ditzelfde fragment
    gebruikt — is 390 px geen randgeval maar de gewone breedte.

    Het label dat tot #1229 boven elk veld stond, wás die scheiding. Deze PR
    haalde het weg: winst op desktop, verlies op een telefoon. Dit zet dat recht.

    **Gemeten op 390 px: 12 px tussen twee rijen, 4 px binnen een rij.** Vóór deze
    regel was het 8 tegenover 8 — even ver, dus geen groepering.

    Twee dingen die ik onderweg fout had en die deze test vormgeven:

    - **Op `top` groeperen deugt niet.** Met `items-center` staat een lage badge
      op dezelfde regel als een hoger veld, maar met een andere `top`. Dat gaf
      drie "regels" en een binnenafstand van −29 px, en dan slaagt de vergelijking
      zonder iets te toetsen. De clustering gaat nu op OVERLAP van de verticale
      bereiken.
    - **Niet elke rij wrapt.** Een rij zonder badge past op 390 px wél op één
      regel. De test zoekt dus de eerste rij die écht wrapt, in plaats van aan te
      nemen dat de eerste dat doet.

    En de klasse is niet de meting: `space-y-*` rekent een sibling met
    `display:none` gewoon mee, dus de marge kan in de DOM staan en niet op het
    scherm — de werkelijke oorzaak van #1197.

    Tegenproef: `gap-y-1` terug naar `gap-2` → binnen wordt 8 px en de verhouding
    zakt naar 12 tegen 8; de assertie op het dubbele valt dan om.
    """
    maten = kaart_telefoon.evaluate("""() => {
      const rijen = [...document.querySelectorAll('[data-email-rij]')]
        .filter(r => r.offsetParent !== null);
      if (rijen.length < 2) return null;
      const doos = r => r.getBoundingClientRect();
      const tussen = Math.round(doos(rijen[1]).top - doos(rijen[0]).bottom);

      // Kinderen clusteren tot visuele REGELS via overlappende verticale
      // bereiken — niet via hun `top`. Zie de docstring.
      const groepeer = (rij) => {
        const k = [...rij.children].map(x => x.getBoundingClientRect())
          .sort((a, b) => a.top - b.top);
        const g = [];
        for (const x of k) {
          const l = g[g.length - 1];
          if (l && x.top < l.onder) l.onder = Math.max(l.onder, x.bottom);
          else g.push({boven: x.top, onder: x.bottom});
        }
        return g;
      };
      const per = rijen.map(groepeer);
      const gewrapt = per.findIndex(g => g.length > 1);
      const binnen = gewrapt >= 0
        ? Math.round(per[gewrapt][1].boven - per[gewrapt][0].onder) : null;
      return {tussen, binnen, gewrapt, regels_per_rij: per.map(g => g.length)};
    }""")
    assert maten, "minder dan twee zichtbare rijen — niets om te groeperen"
    assert maten["gewrapt"] >= 0, (
        f"geen enkele rij wrapt op deze breedte, dus deze test meet de groepering niet: {maten}"
    )
    assert maten["binnen"] is not None and maten["binnen"] >= 0, (
        f"onzinnige binnenafstand ({maten['binnen']}) — dan toetst de vergelijking "
        f"hieronder niets: {maten}"
    )
    assert maten["tussen"] >= 12, f"te weinig ruimte tussen twee rijen: {maten['tussen']} px"
    assert maten["tussen"] >= 2 * maten["binnen"], (
        f"het gat tussen twee rijen ({maten['tussen']} px) is niet duidelijk "
        f"groter dan dat binnen een rij ({maten['binnen']} px) — dan hoort de "
        "verwijderknop visueel bij de verkeerde rij"
    )
