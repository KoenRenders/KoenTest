"""#870-G — from the landing page, click through to every tenant.

Koen, 11 September 2026: *"and also whether you end up at the right tenant — platform,
Millegem, raakvoorbeeld"*, and then: **this starts from the platform landing page.**

So not a unit test on the resolution function but the road a person walks: open the
landing, click a card, and establish where you end up. That form covers the whole chain —
the card must carry the right address, that address must answer, and behind it the right
tenant must stand. Three things that each failed separately this release: #853 (every path
but the root fell back to an afdeling), #860 (the cards carried another afdeling's address)
and #866 (the platform domain came out on Raak Millegem). The dead card on PROD last night
would have failed here too, because a click that arrives nowhere is a failing test.

**Which tenant, not "something answered with 200".** The wrong tenant answers 200 just as
happily; the afdeling name on the screen is the evidence.

**The trap of this test, and it is the reason for the explicit check below.** The landing
only appears when the host is in `PLATFORM_HOSTS`. If the e2e setup does not arrange that,
the test does not find its starting point — and a test that cannot find its starting point
must not go green. Same mistake as the fourteen gates in #678 that fetched their files
without checking they found any. `scripts/e2e-local.sh` therefore sets
`PLATFORM_HOSTS=platform.localhost`, and the first assertion here is that the landing is
really there.

Broken on purpose, and this is the proof the issue asks for: `PLATFORM_HOSTS` removed from
`scripts/e2e-local.sh` → **all four fall over**, starting with the landing itself. Not one
of them slips through green without its starting point.

A second one, found while writing: the first version asserted "Digital Platform" is absent
once you have clicked through. That failed on the demo afdeling, which names *"het Raak
Digital Platform"* in her own intro text. The assertion now reads `data-shell` — what the
answer says about its own shell — instead of the copy. A text hit is not a location.

**What this does NOT catch, and it should be said.** What went wrong on PROD was
configuration: `PLATFORM_HOSTS` named a host the proxy did not serve. In a setup where the
e2e harness sets both itself, that difference is invisible. That hole was closed by #866 —
one source for that address — and not here.
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE  # noqa: E402

# Dezelfde poort als de rest van de suite, andere hostnaam: zo is de landing bereikbaar
# zonder dat élk ander e2e-verzoek een platformverzoek wordt.
PLATFORM = BASE.replace("127.0.0.1", "platform.localhost")


@pytest.fixture(scope="module")
def pagina():
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page()
        yield page
        browser.close()


def _tekst(page) -> str:
    return page.locator("body").inner_text()


def test_de_landing_toont_de_afdelingen(pagina):
    """Het beginpunt. Faalt dit, dan zegt de rest van dit bestand niets — daarom staat
    het er apart en niet als aanname."""
    pagina.goto(PLATFORM + "/", wait_until="domcontentloaded")

    tekst = _tekst(pagina)
    assert "Digital Platform" in tekst, (
        f"geen landingspagina op {PLATFORM} — staat de host in PLATFORM_HOSTS? "
        f"Zonder beginpunt bewijst deze suite niets.\n{tekst[:300]}")
    kaarten = pagina.locator("main a[href]")
    assert kaarten.count() >= 2, f"maar {kaarten.count()} kaart(en) op de landing"


@pytest.mark.parametrize("code,naam", [
    ("raakmillegem", "Millegem"),
    ("raakvoorbeeldafdeling", "Voorbeeldafdeling"),
])
def test_doorklikken_komt_bij_de_juiste_afdeling_uit(pagina, code, naam):
    """Per bestemming: WELKE tenant bereik je. Een 200 is het bewijs niet — de verkeerde
    afdeling antwoordt even goed met 200."""
    pagina.goto(PLATFORM + "/", wait_until="domcontentloaded")
    kaart = pagina.locator(f'main a[href*="{code}"]').first
    assert kaart.count() > 0, f"geen kaart die naar {code} wijst op de landing"

    kaart.click()
    pagina.wait_for_load_state("domcontentloaded")

    assert code in pagina.url, f"geklikt naar {code}, beland op {pagina.url}"
    tekst = _tekst(pagina)
    assert naam in tekst, (
        f"de kaart van {code} komt uit bij een andere afdeling — op het scherm staat "
        f"niet '{naam}'.\n{tekst[:300]}")
    # Op de SCHIL en niet op de tekst: de demo-afdeling noemt "het Raak Digital Platform"
    # in haar eigen intro, dus een tekstvondst zou hier een bevinding over inhoud zijn en
    # niet over waar je staat. `data-shell` is wat het antwoord zelf over zijn schil zegt.
    assert pagina.locator("body").get_attribute("data-shell") != "platform", (
        "je staat nog op de landingspagina; de klik heeft je nergens gebracht")


def test_de_terugweg_houdt_je_op_dezelfde_afdeling(pagina):
    """Waar iemand zich vergist: na een pad-prefix volgt de navigatie absolute paden.

    Dat is precies wat #853 was — je kwam binnen bij de ene afdeling en stond na één klik
    bij de andere. De tenant-cookie hoort je te houden waar je was.
    """
    pagina.goto(PLATFORM + "/raakvoorbeeldafdeling/", wait_until="domcontentloaded")
    assert "Voorbeeldafdeling" in _tekst(pagina), "opzet klopt niet"

    pagina.goto(PLATFORM + "/activiteiten", wait_until="domcontentloaded")

    tekst = _tekst(pagina)
    assert "Voorbeeldafdeling" in tekst and "Raak Millegem" not in tekst, (
        f"na een absoluut pad sta je bij een andere afdeling — dat is #853\n{tekst[:300]}")
