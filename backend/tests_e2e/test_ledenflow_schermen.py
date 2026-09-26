"""E2E #1183: de schermen die de schermafdruk-tool van de ledenflow vastlegt.

`tests_e2e/screenshots.py` is gereedschap en geen test — het wordt niet door
pytest verzameld en het bewijst dus niets over wat er op de beelden staat. Deze
tests staan ernaast en bewaken precies dat: **toont het scherm werkelijk wat de
afdruk moet tonen?**

Zonder hen legt de tool een leeg scherm vast en merkt niemand het. Dat is geen
theoretisch gevaar: de e2e-seed maakt een gezin met een lidmaatschap voor het
LOPENDE jaar, en dat gezin toont geen vernieuwknop. Een afdruk "verlengen" van
dat gezin zou een portaal zonder knop zijn, en op de uitlegpagina zou die
afbeelding iets beloven wat er niet staat.

Vandaar twee extra seed-gezinnen (#1183), elk voor één toestand die het eerste
niet kan tonen. De test hieronder toetst alle drie de toestanden náást elkaar —
dat de knop er is bij het verlopen gezin bewijst pas iets als je ook ziet dat hij
er níét is bij het gezin dat in orde is.
"""
import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie  # noqa: E402

VERLENGKNOP = "Lidmaatschap vernieuwen"


def _sessie(email: str) -> str:
    from app.domains.auth.api import make_session_value

    return make_session_value(email)


@pytest.fixture(scope="module")
def browser_page():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
        yield page
        browser.close()


def _portaal(page, email: str):
    page.context.clear_cookies()
    login_met_sessie(page, _sessie(email))
    page.goto("/leden/gezin")
    page.wait_for_selector("main", timeout=5000)
    return page


def test_de_drie_ledentoestanden_tonen_elk_iets_anders(browser_page):
    """De kern van #1183, en de reden dat er twee gezinnen bijgekomen zijn.

    Drie portalen naast elkaar:

    - het seed-gezin (lidmaatschap loopt) → **geen** vernieuwknop;
    - het verlopen gezin → **wel** een vernieuwknop.

    Twee toestanden naast elkaar, want "de knop staat er bij het verlopen gezin"
    bewijst pas iets als je ook ziet dat hij er níét staat bij het gezin dat in
    orde is.

    Tegenproef, letterlijk de proef die het issue vraagt: het lidmaatschap van het
    verlopen gezin op het LOPENDE jaar gezet → de vernieuwknop verdwijnt en deze
    test faalt op de tweede assertie. Daarmee is bewezen dat de afdruk niet
    toevallig goed staat.
    """
    from seed_e2e import MARKER_EMAIL, MARKER_EMAIL_VERLOPEN

    page = _portaal(browser_page, MARKER_EMAIL)
    expect(page.get_by_role("button", name=VERLENGKNOP)).to_have_count(0)

    page = _portaal(browser_page, MARKER_EMAIL_VERLOPEN)
    expect(page.get_by_role("button", name=VERLENGKNOP)).to_be_visible()


def test_er_staat_geen_naam_uit_de_ledenadministratie_op(browser_page):
    """#1183, punt 4 — de reden dat deze beelden niet met de hand genomen worden.

    HDEV draagt echte ledenrecords; een afdruk daarvan zet naam en adres van een
    echt lid op een publieke pagina, en dat is een lek dat geen grep ooit vindt
    omdat het in een afbeelding zit. De tool weigert al een niet-lokale host; deze
    test controleert de andere kant — dat wat er op het scherm staat uit de seed
    komt.

    Toetst op de HERKOMST en niet op een lijst echte namen: zo'n lijst zou zelf een
    ledenlijst in de repo zijn. Elk gezinslid op het portaal draagt een achternaam
    die déze seed maakt; staat er een andere, dan komt hij uit de
    ledenadministratie.

    #1208: dat was een voorvoegselcontrole ("heet het E2E …?") zolang de
    seed-gezinnen "E2E Seed" en "E2E Verlopen" heetten. Die namen lazen op een
    publieke uitlegpagina als een foutmelding en zijn Jommeke en Gobelijn geworden,
    waarmee het gedeelde voorvoegsel verdween. De lijst komt daarom uit
    `seed_e2e.SEED_ACHTERNAMEN` en niet uit dit bestand — een eigen kopie zou na de
    volgende hernoeming groen blijven staan zonder nog iets te toetsen.
    """
    from seed_e2e import MARKER_EMAIL, MARKER_EMAIL_VERLOPEN, SEED_ACHTERNAMEN

    for email in (MARKER_EMAIL, MARKER_EMAIL_VERLOPEN):
        page = _portaal(browser_page, email)
        # De naam staat in een `span.font-semibold` binnen de leesweergave van de
        # gezinslidkaart; er is geen kop-element. Gevonden doordat de assertie
        # hieronder een lege lijst betrapte in plaats van vacuüm te slagen.
        namen = page.locator("div.space-y-4 span.font-semibold").all_inner_texts()
        assert namen, f"geen gezinslid op het portaal van {email}"
        for naam in namen:
            assert any(naam.strip().endswith(a) for a in SEED_ACHTERNAMEN), (
                f"{naam!r} draagt geen achternaam uit de seed "
                f"({', '.join(SEED_ACHTERNAMEN)}) — dit portaal toont iemand uit "
                "de ledenadministratie en hoort niet op een publieke pagina")
