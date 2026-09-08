"""E2E: de bevestiging na "Opslaan" komt écht op het scherm (#717).

Deze weg is met pytest niet te bewijzen. De servertest toont dat het antwoord een
element met `hx-swap-oob="afterbegin:#toasts"` bevat — meer niet. Wat daarna moet
gebeuren, gebeurt in de browser:

1. htmx haalt het oob-element uit het antwoord vóór de gewone swap,
2. zet de KINDEREN ervan vooraan in `#toasts`,
3. Alpine initialiseert die nieuwe knoop (x-show + de setTimeout uit `ui.toast()`),
4. en de toast verdwijnt weer.

Stap 3 is de reden dat dit bestand bestaat: een out-of-band ingevoegde knoop komt
niet via een paginalading binnen, dus of Alpine hem oppikt hangt van zijn
mutatie-observer af. `ui.toast()` stond sinds #528 in de kit maar was tot #717
door geen enkele template aangeroepen — het contract was dus nooit uitgeprobeerd,
alleen opgeschreven.

Kapotgemaakt om te controleren dat deze test rood kan worden: het succespad van
`inschrijving_opslaan` teruggezet op `edit_open=True` zonder `toast=` — dan faalt
hij op de eerste assert (geen toast in #toasts) en, na die assert weg te halen,
ook op de bewerkmodus die blijft staan.
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import (BASE, Betalingenscherm,  # noqa: E402
                                Inschrijvingsdetail, login_als_admin, toasts)


def _ontbreekt(reden: str) -> None:
    """Zelfde afspraak als de beheerflows (#644): tegen een echte omgeving is een
    skip terecht, onder de e2e-seed is dezelfde melding een bevinding."""
    if os.environ.get("E2E_SEEDED") == "1":
        pytest.fail(f"e2e-seed geladen maar: {reden}")
    pytest.skip(reden)


@pytest.fixture(scope="module")
def admin_page():
    try:
        from app.domains.auth.api import make_session_value
        from tests.conftest import SEEDED_ADMIN_EMAIL

        email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    except Exception as exc:  # pragma: no cover - alleen in een kale omgeving
        pytest.skip(f"backend niet importeerbaar voor de sessiewaarde: {exc}")

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE)
        login_als_admin(page, email, make_session_value(email))
        page.goto("/admin/betalingen")
        if page.locator("main").count() == 0:
            browser.close()
            pytest.skip("adminsessie niet aanvaard door deze omgeving")
        yield page
        browser.close()


def test_opslaan_toont_een_toast_en_sluit_het_paneel(admin_page):
    """Het gemelde geval: klikken op Opslaan gaf geen enkel teken van leven."""
    betalingen = Betalingenscherm(admin_page).open()
    paneel = betalingen.bewerkbaar_detailpaneel()
    if paneel is None:
        _ontbreekt("geen bewerkbare inschrijving op deze omgeving")

    detail = Inschrijvingsdetail(paneel)
    detail.bewerken()
    if detail.aantalvelden().count() == 0:
        _ontbreekt("geen bestelregels om te wijzigen")

    detail.zet_aantal(0, 2)
    detail.opslaan()

    melding = toasts(admin_page).first
    melding.wait_for(state="visible", timeout=5000)
    assert "opgeslagen" in melding.inner_text().lower(), melding.inner_text()

    # En het paneel is dicht: de knop staat er niet meer, dus de reflex om nog eens
    # te klikken bestaat niet meer.
    assert not detail.staat_in_bewerkmodus(), (
        "het paneel staat na Opslaan nog in bewerkmodus")


def test_de_toast_verdwijnt_weer(admin_page):
    """Bewijst dat Alpine de out-of-band ingevoegde knoop initialiseert.

    Zonder die initialisatie blijft de toast staan: `x-show` en de setTimeout uit
    `ui.toast()` worden dan nooit uitgevoerd. Hij zou er dus wél staan — de vorige
    test blijft groen — en toch nooit meer weggaan. Dat is precies het stuk van het
    contract dat niemand ooit had uitgeprobeerd.
    """
    betalingen = Betalingenscherm(admin_page).open()
    paneel = betalingen.bewerkbaar_detailpaneel()
    if paneel is None:
        _ontbreekt("geen bewerkbare inschrijving op deze omgeving")

    detail = Inschrijvingsdetail(paneel)
    detail.bewerken()
    if detail.aantalvelden().count() == 0:
        _ontbreekt("geen bestelregels om te wijzigen")

    detail.zet_aantal(0, 3)
    detail.opslaan()

    melding = toasts(admin_page).first
    melding.wait_for(state="visible", timeout=5000)
    # De macro zet standaard 4000 ms; ruim wachten en dan pas oordelen.
    melding.wait_for(state="hidden", timeout=15000)
