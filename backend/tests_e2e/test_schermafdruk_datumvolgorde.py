"""E2E #1238 punt 2: het geboortedatumveld staat op de afdruk in de Belgische volgorde.

Op `leden-gezin-bewerken` toonde het veld `10/30/1955`. Dat is niet de site: een native
`<input type="date">` laat de BROWSER de veldvolgorde kiezen, en de opname draaide in de
standaardtaal. De uitlegpagina zou leden zo een volgorde aanleren die ze op de site nooit
te zien krijgen.

**Hoe je die volgorde meet.** Uit de DOM is ze niet te lezen: de segmenten van een
datumveld leven in een gesloten shadow-tree, en Chromiums accessibility-boom geeft voor
dit veld alleen het label *Geboortedatum* terug (beide nagegaan tijdens het bouwen —
`page.accessibility` bestaat niet meer in deze Playwright, en
`Accessibility.getPartialAXTree` over CDP levert niets meer). De pijltoets wél: ze
verhoogt het segment waar de cursor staat, en na een klik staat die op het **eerste**
segment. Dus:

    1955-10-30 + ArrowUp → 1955-10-**31**   de dag staat vooraan (dd/mm/jjjj)
    1955-10-30 + ArrowUp → 1955-**11**-30   de maand staat vooraan (mm/dd/yyyy)

Dat is de hele test, en het is een meting van het gerenderde veld in plaats van van de
oorzaak erachter. Dat verschil deed er hier toe: een eerdere versie van deze reparatie
zette alleen `locale="nl-BE"` op de context. `navigator.language` zei dan keurig `nl-BE`,
`Intl` zei `day-month-year` en zelfs de pixels van het veld verschilden — en op de afdruk
stond nog altijd `10/30/1955`. De veldvolgorde komt uit de taal van het BROWSERPROCES,
niet uit die van de context.

Rood gemaakt om te toetsen dát ze kunnen falen: met `env` uit `launch_opties()` gehaald
verhoogt de pijltoets weer de maand en falen beide tests.
"""

import os
import sys

from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie  # noqa: E402
from tests_e2e.screenshots import context_opties, launch_opties  # noqa: E402

# De waarde die de seed in dit veld zet (#1238 punt 3). Dag en maand verschillen, dus
# de pijltoets verraadt welk segment vooraan staat.
GEZAAIDE_DATUM = "1955-10-30"
DAG_VOORAAN = "1955-10-31"
MAAND_VOORAAN = "1955-11-30"


def _eerste_segment(launch_kwargs: dict, context_kwargs: dict) -> dict:
    """Open het bewerkformulier van het eerste gezinslid en duw op het datumveld."""
    from app.domains.auth.api import make_session_value
    from seed_e2e import MARKER_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        opstart = dict(launch_kwargs)
        if exe:
            opstart["executable_path"] = exe
        browser = pw.chromium.launch(**opstart)
        try:
            context = browser.new_context(
                base_url=BASE, viewport={"width": 1440, "height": 900}, **context_kwargs
            )
            page = context.new_page()
            login_met_sessie(page, make_session_value(MARKER_EMAIL))
            page.goto("/leden/gezin")
            page.wait_for_selector("main", timeout=5000)
            page.get_by_role("button", name="Bewerken").first.click()
            veld = page.locator("input[id$='-date_of_birth']").first
            veld.wait_for(state="visible", timeout=5000)
            voor = veld.input_value()
            veld.click()
            page.keyboard.press("ArrowUp")
            return {
                "voor": voor,
                "na": veld.input_value(),
                "taal": page.evaluate("navigator.language"),
            }
        finally:
            browser.close()


def test_de_opname_zet_de_dag_vooraan():
    """Met de opstart- én contextinstellingen van de tool zelf, niet met nagetypte."""
    meting = _eerste_segment(launch_opties(), context_opties())
    assert meting["voor"] == GEZAAIDE_DATUM, (
        f"het veld draagt niet de gezaaide geboortedatum maar {meting['voor']!r} — "
        "deze test meet dan iets anders dan ze denkt"
    )
    assert meting["na"] == DAG_VOORAAN, (
        f"de pijltoets verhoogde {meting['voor']} naar {meting['na']}: het eerste "
        "segment is niet de dag, dus de afdruk draagt nog de Amerikaanse volgorde"
    )
    assert meting["taal"] == "nl-BE", (
        f"navigator.language staat op {meting['taal']!r} — de pagina zelf formatteert "
        "dan nog in een andere taal dan het datumveld"
    )


def test_zonder_de_taal_van_de_tool_staat_de_maand_vooraan():
    """De tegenproef, en tegelijk de reden dat deze test op het proces let.

    Zonder deze meting kan de volgende die hier iets wijzigt niet zien wélke van de twee
    taalinstellingen het veld stuurt — en dan komt de context-locale terug als "de"
    reparatie, met een afdruk die er niets van merkt.
    """
    meting = _eerste_segment({}, {"reduced_motion": "reduce"})
    assert meting["na"] == MAAND_VOORAAN, (
        f"een browser zonder de taal van de tool verhoogde {meting['voor']} naar "
        f"{meting['na']}; verwacht was de maand — meet deze test nog wat ze zegt?"
    )
