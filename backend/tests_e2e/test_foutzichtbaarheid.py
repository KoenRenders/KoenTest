"""E2E: een mislukte htmx-actie is ZICHTBAAR (#649).

De ontbrekende invariant was niet dat een actie kan falen — dat mag — maar dat
falen zichtbaar is. Op HDEV stonden elf opeenvolgende `POST … -> 403` in het
toegangslog terwijl er op het scherm niets gebeurde: geen swap, geen melding,
geen redirect. Voor de gebruiker is dat niet te onderscheiden van een kapotte
toepassing, en dat is precies hoe het gemeld werd ("het systeem doet vreemd").

Alleen een echte browser kan dit bewijzen. De server deed niets fout — hij gaf
netjes 403 — en de markup was in orde; de fout zat in wat de pagina met dat
antwoord deed, en dat is per definitie gedrag in de browser.
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, Activiteitdetail, login_als_admin  # noqa: E402


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
        page.goto("/admin/activiteiten")
        if page.locator("main").count() == 0:
            browser.close()
            pytest.skip("adminsessie niet aanvaard door deze omgeving")
        yield page
        browser.close()


def test_een_403_levert_een_zichtbare_melding(admin_page):
    """Het gemelde geval: opslaan met een verlopen CSRF-token.

    De assert gaat over wat de gebruiker ziet, niet over de statuscode — die was
    altijd al 403. Wat ontbrak, was de melding.
    """
    scherm = Activiteitdetail(admin_page)
    if not scherm.open_eerste():
        _ontbreekt("geen activiteit om te openen")
    if scherm.datumregel().count() == 0:
        _ontbreekt("de activiteit heeft geen datumregel om te bewerken")

    scherm.breek_het_csrf_token()
    scherm.bewerk_de_eerste_datum()
    scherm.bewaar()

    melding = scherm.foutmeldingen().first
    melding.wait_for(state="visible", timeout=5000)
    assert "sessie" in melding.inner_text().lower(), (
        f"een 403 hoort te zeggen wat de gebruiker moet doen, kreeg: {melding.inner_text()!r}")


def test_herhaald_mislukken_geeft_niet_elf_meldingen(admin_page):
    """Op HDEV stonden elf identieke 403's achter elkaar (#649).

    Elf keer dezelfde rode melding stapelen is zijn eigen soort ruis; de gebruiker
    leert er niets bij na de eerste.
    """
    scherm = Activiteitdetail(admin_page)
    if not scherm.open_eerste():
        _ontbreekt("geen activiteit om te openen")
    if scherm.datumregel().count() == 0:
        _ontbreekt("de activiteit heeft geen datumregel om te bewerken")

    scherm.breek_het_csrf_token()
    scherm.bewerk_de_eerste_datum()
    for _ in range(3):
        scherm.bewaar()
        admin_page.wait_for_timeout(200)

    assert scherm.foutmeldingen().count() == 1, (
        f"drie mislukte pogingen gaven {scherm.foutmeldingen().count()} meldingen")
