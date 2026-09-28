"""E2E #1241: de schermen van de verlengflow die de schermafdruk-tool vastlegt.

`tests_e2e/screenshots.py` is gereedschap en geen test: het bewijst niets over wat er
op de beelden staat. Deze tests staan ernaast en bewaken dat de drie toestanden elk
werkelijk tonen wat de uitlegpagina erover gaat vertellen.

Drie toestanden, en ze zijn alleen samen iets waard — "de betaalinstructies staan er
bij het overschrijvingsgezin" bewijst pas iets als je ook ziet dat ze er bij de andere
twee níét staan:

- het seed-gezin, dekking tot eind dit jaar, venster open → de keuze plus de knop;
- het vernieuwde gezin, dekking tot eind volgend jaar → **geen** vernieuwblok meer.
  Dat is de regel uit #496: `renewal_available()` verbergt de knop zodra de dekking het
  volgende jaar bereikt, zodat een tweede poging niet op een 409 "al vernieuwd" botst;
- het overschrijvingsgezin, vernieuwing loopt → bedrag, IBAN, begunstigde en mededeling.

**En de valkuil die dit issue eigenlijk is.** Een openstaande betaling in de gedeelde
seed is precies de rij die `test_beheer_flows` als eerste "Bevestig" oppikt — gemeten in
#1183: die test zette hem op betaald, waarna het scherm verdween én die test iets anders
toetste dan zijn naam belooft. Vandaar een eigen gezin per toestand, en vandaar de
laatste test hieronder, die bewaakt dat de nieuwe rij níét vooraan komt.
"""

import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, Betalingenscherm, login_met_sessie  # noqa: E402

VERLENGKNOP = "Lidmaatschap vernieuwen"
BETAALINSTRUCTIE = "Vernieuwing geregistreerd"


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


def test_het_vernieuwde_gezin_toont_geen_vernieuwblok_meer(browser_page):
    """Afdruk 2: wat een lid ziet nadat de online betaling gelukt is.

    De dekking loopt tot eind volgend jaar en het vernieuwblok is weg. Rood te maken
    door het lidmaatschap van dat gezin op het lopende jaar te zetten: dan staat de
    knop er weer en toont de afdruk dezelfde toestand als `leden-gezin`.
    """
    from datetime import date

    from seed_e2e import MARKER_EMAIL_VERNIEUWD

    page = _portaal(browser_page, MARKER_EMAIL_VERNIEUWD)
    volgend = date.today().year + 1
    assert f"31-12-{volgend}" in page.locator("main").inner_text(), (
        "de dekking loopt niet tot eind volgend jaar; dit is de toestand ná de betaling"
    )
    expect(page.get_by_role("button", name=VERLENGKNOP)).to_have_count(0)
    assert BETAALINSTRUCTIE not in page.locator("main").inner_text(), (
        "er staan betaalinstructies op een gezin dat al betaald heeft"
    )


def test_het_overschrijvingsgezin_toont_bedrag_iban_begunstigde_en_mededeling(browser_page):
    """Afdruk 3, en het beeld waar de uitlegpagina het meest aan heeft.

    Alle vier de gegevens apart getoetst en niet alleen "het blok staat er": IBAN en
    begunstigde komen sinds migratie 119 uit de organisatie-entiteit, en de sjabloon
    verbergt een lege waarde stil. Zonder deze asserties zou een beeld zonder
    rekeningnummer er geslaagd uitzien.
    """
    from seed_e2e import (
        MARKER_EMAIL_OVERSCHRIJVING,
        OVERSCHRIJVING_OGM,
        SEED_BEGUNSTIGDE,
        SEED_IBAN,
    )

    page = _portaal(browser_page, MARKER_EMAIL_OVERSCHRIJVING)
    tekst = page.locator("main").inner_text()

    assert BETAALINSTRUCTIE in tekst, f"geen betaalinstructies op het scherm: {tekst!r}"
    # Met een KOMMA (#1241): op het beeld stond `€ 20.00`, en een punt op een
    # Belgische betaalinstructie is de laatste plek waar je twijfel wil. De opmaak zelf
    # staat in `tests/test_bedrag_op_de_vernieuwing_1241.py`; hier telt dat het op het
    # échte scherm zo aankomt.
    assert "20,00" in tekst, f"geen bedrag in Belgische notatie: {tekst!r}"
    assert SEED_IBAN in tekst, f"geen rekeningnummer: {tekst!r}"
    assert SEED_BEGUNSTIGDE in tekst, f"geen begunstigde: {tekst!r}"
    assert OVERSCHRIJVING_OGM in tekst, f"geen mededeling: {tekst!r}"
    expect(page.get_by_role("button", name=VERLENGKNOP)).to_have_count(0)


def test_de_openstaande_vernieuwing_komt_niet_vooraan_bij_de_betalingen(browser_page):
    """De tegenproef op de valkuil van dit issue.

    `test_beheer_flows` neemt de EERSTE rij met een "Bevestig"-knop. Het
    betalingenscherm sorteert `created_at.desc()`, dus een rij die als laatste ontstaat
    komt bovenaan — en dan bevestigt die test voortaan de vernieuwing van dit issue in
    plaats van de inschrijving die ze bedoelt, waarmee ook afdruk 3 verdwijnt.

    Daarom draagt die betaling in de seed een `created_at` van een maand terug, en deze
    test bewaakt de uitkomst: de eerste "Bevestig"-rij mag niet die van de vernieuwing
    zijn, en de vernieuwing moet er wél tussen staan — anders toetst dit niets.

    **Rood gemaakt, en de eerste poging mislukte.** Met de `created_at` helemaal uit de
    seed gehaald bleef deze test groen (3 passed): de inschrijvingsbetalingen ontstaan
    verderop in `seed_e2e.py` en zijn dus jonger, dus de vernieuwing stond ook zonder
    die regel niet vooraan. De bescherming kwam dan uit de volgorde van de blokken in
    dat bestand — precies wat de expliciete datum wegneemt. Met `created_at` op morgen
    komt de rij wél vooraan en faalt de laatste assertie met
    `+++000/0000/40416+++` erin. Dát is de meting die telt.
    """
    from seed_e2e import OVERSCHRIJVING_OGM
    from tests.conftest import SEEDED_ADMIN_EMAIL

    browser_page.context.clear_cookies()
    login_met_sessie(browser_page, _sessie(SEEDED_ADMIN_EMAIL))
    browser_page.set_viewport_size({"width": 1440, "height": 900})
    try:
        Betalingenscherm(browser_page).open()
        rijen = browser_page.locator(
            "#betalingen-lijst tbody tr",
            has=browser_page.get_by_role("button", name="Bevestig", exact=True),
        )
        mededelingen = []
        for i in range(rijen.count()):
            mono = rijen.nth(i).locator(".font-mono")
            if mono.count():
                mededelingen.append(mono.first.inner_text().strip())

        assert mededelingen, "geen enkele rij met een Bevestig-knop op het scherm"
        assert OVERSCHRIJVING_OGM in mededelingen, (
            "de openstaande vernieuwing staat niet tussen de bevestigbare rijen; deze "
            "test kan dan niet meten of ze vooraan komt"
        )
        assert mededelingen[0] != OVERSCHRIJVING_OGM, (
            f"de vernieuwing van #1241 staat vooraan ({mededelingen[0]}) — "
            "`test_beheer_flows` bevestigt voortaan die rij en afdruk 3 verdwijnt"
        )
    finally:
        browser_page.set_viewport_size({"width": 390, "height": 844})
