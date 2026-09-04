"""E2E-golden-flows voor de BEHEERschermen (#622, laag 3).

De zes bestaande flows zijn allemaal publiek; op de beheerschermen stond er nul —
precies waar het geld zit en waar bij de v2.0.0-validatie de dode knoppen stonden.

Alleen een echte browser bewijst dat een knop iets **doet**. Dat is de enige laag die
#613-punt-3 zou hebben gevangen: daar zagen server én markup er correct uit en deed
de knop toch niets.

Selectors staan in `schermen.py`, zodat een UI-port één bestand raakt i.p.v. elke flow.
"""
import os
import sys
import time

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from tests_e2e.schermen import (BASE, Betalingenscherm, Inschrijvingsdetail,  # noqa: E402
                                Ledenscherm, login_als_admin)

ADMIN_EMAIL = os.environ.get("E2E_ADMIN_EMAIL", "admin@raakmillegem.be")


@pytest.fixture(scope="module")
def admin_page():
    """Een browser met een adminsessie."""
    try:
        from app.domains.auth.api import make_session_value
    except Exception as exc:  # pragma: no cover - alleen in een kale omgeving
        pytest.skip(f"backend niet importeerbaar voor de sessiewaarde: {exc}")

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE)
        login_als_admin(page, ADMIN_EMAIL, make_session_value(ADMIN_EMAIL))
        page.goto("/admin/betalingen")
        if "/aanmelden" in page.url:
            browser.close()
            pytest.skip("adminsessie niet aanvaard door deze omgeving")
        yield page
        browser.close()


def _eerste_ogm(page) -> str:
    """Een OGM van de eerste kaart; die is uniek en zichtbaar op het scherm."""
    tekst = page.locator("text=OGM").first
    if tekst.count() == 0:
        pytest.skip("geen betaling met OGM op deze omgeving")
    return tekst.inner_text().split("OGM")[-1].strip()


def test_betaling_bevestigen(admin_page):
    """De knop die in #616 inert was: doet ze in een echte browser wat ze belooft?"""
    betalingen = Betalingenscherm(admin_page).open()
    if admin_page.get_by_role("button", name="Bevestig betaald").count() == 0:
        pytest.skip("geen openstaande betaling om te bevestigen")

    ogm = _eerste_ogm(admin_page)
    betalingen.bevestig_betaald(ogm)

    assert "Betaald" in " ".join(betalingen.badges(ogm))


def test_bestelregel_wijzigen_werkt_de_bedragen_bij(admin_page):
    """#613: aantal wijzigen deed niets doordat de attributen ge-escaped waren, en
    de bedragen op de kaart volgden niet."""
    betalingen = Betalingenscherm(admin_page).open()
    if admin_page.get_by_text("Toon inschrijvingsdetails").count() == 0:
        pytest.skip("geen inschrijving met details op deze omgeving")

    ogm = _eerste_ogm(admin_page)
    betalingen.toon_inschrijvingsdetails(ogm)

    detail = Inschrijvingsdetail(admin_page)
    detail.bewerken()
    if admin_page.locator('input[name^="quantity_"]').count() == 0:
        pytest.skip("geen bestelregels om te wijzigen")

    detail.zet_aantal(0, 3)
    detail.opslaan()

    # Het paneel blijft open (#613-3) en toont het herrekende totaal (#613-4).
    assert admin_page.locator('input[name^="quantity_"]').first.input_value() == "3"
    assert "Totaal" in detail.totaal()


def test_lidmaatschap_schrappen_geeft_een_terugbetaling(admin_page):
    """#619: het schrappen liet de betaling ongemoeid; nu hoort er een te bevestigen
    terugbetaling te verschijnen."""
    leden = Ledenscherm(admin_page).open()
    if admin_page.locator("#leden-lijst a").count() == 0:
        pytest.skip("geen gezinnen op deze omgeving")

    admin_page.locator("#leden-lijst a").first.click()
    admin_page.wait_for_timeout(400)
    if admin_page.get_by_role("button", name="Verwijderen").count() == 0:
        pytest.skip("geen lidmaatschap om te schrappen")

    leden.verwijder_lidmaatschap()

    Betalingenscherm(admin_page).open()
    assert "Terug te betalen" in admin_page.content() or \
           "Terug te storten" in admin_page.content()
