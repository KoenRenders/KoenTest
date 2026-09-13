"""Klikt een jaartal in de draaitabel écht door? (#899 stap 2)

Deze test bestaat om een reden die pijnlijk herkenbaar is: het onderdeel stond er
en de verbinding niet. De drill-knop werd gerenderd met de juiste naam en de juiste
waarde, en de eenheidstests keken naar de markup en naar de route — allebei groen.
Maar de knop droeg geen `hx-get`, en `type="button"` verstuurt niets. Klikken deed
letterlijk niets.

De oorzaak zat in de reden die in het commentaar van de macro stond: de kit kent
dit domein niet en kreeg dus een naam om terug te sturen — maar ze kende evenmin de
URL waar dat heen moest, en die was nergens meegegeven.

**Alleen een echte browser bewijst dat een knop iets doet.** Een eenheidstest die
vaststelt dat het element doorklikbaar gerenderd is, herhaalt precies de blinde
vlek: ze leest dezelfde markup waarin het ontbrak.

Zelfde vorm als #613 punt 3 en als de `sort_order` die uit het formulier verdween
terwijl de route hem nog aannam.
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_als_admin  # noqa: E402

# Een draaitabel op jaar met één maat en geen kolomas: de kortste weg naar een
# scherm waarin een jaartal doorklikbaar hoort te zijn.
PANEEL = ("/admin/rapporten/paneel?object=date_year&object=payment_amount"
          "&layout=pivot&pivot_column=&no_column=1")


def _admin_email() -> str:
    override = os.environ.get("E2E_ADMIN_EMAIL")
    if override:
        return override
    from tests.conftest import SEEDED_ADMIN_EMAIL

    return SEEDED_ADMIN_EMAIL


@pytest.fixture(scope="module")
def admin_page():
    try:
        from app.domains.auth.api import make_session_value

        email = _admin_email()
    except Exception as exc:  # pragma: no cover
        pytest.skip(f"backend niet importeerbaar voor de sessiewaarde: {exc}")

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE)
        login_als_admin(page, email, make_session_value(email))
        page.goto("/admin/rapporten")
        if page.locator("text=Rapporten").count() == 0:
            browser.close()
            pytest.skip("adminsessie niet aanvaard door deze omgeving")
        yield page
        browser.close()


def test_klikken_op_een_jaartal_drilt_naar_kwartaal(admin_page):
    """De klik, in een echte browser — niet de markup en niet de route."""
    admin_page.goto(PANEEL)
    knop = admin_page.locator('button[name="drill"]').first
    if knop.count() == 0:
        pytest.skip("geen betalingen in deze omgeving, dus geen jaartal om te "
                    "drillen")

    jaar = knop.inner_text().strip()
    knop.click()
    admin_page.wait_for_timeout(800)

    inhoud = admin_page.content()
    assert 'name="object" value="date_quarter"' in inhoud, (
        "na de klik hoort het rapport op kwartaal te staan; gebeurt er niets, "
        "dan mist de knop zijn hx-get en is de markup alleen decor")
    assert f'value="{jaar}"' in inhoud, (
        "en de filter op het aangeklikte jaar hoort zichtbaar in de staat te staan")


def test_terug_omhoog_brengt_je_terug(admin_page):
    """De weg terug, ook door de browser: één knop, één niveau omhoog."""
    admin_page.goto(PANEEL)
    knop = admin_page.locator('button[name="drill"]').first
    if knop.count() == 0:
        pytest.skip("geen betalingen in deze omgeving")
    knop.click()
    admin_page.wait_for_timeout(800)

    terug = admin_page.locator('button[name="rollup"]').first
    assert terug.count() > 0, "na het drillen hoort er een weg terug te staan"
    terug.click()
    admin_page.wait_for_timeout(800)

    inhoud = admin_page.content()
    assert 'name="object" value="date_year"' in inhoud
    assert 'name="filter" value="date_year"' not in inhoud, (
        "oprollen hoort de filter mee terug te nemen; blijft hij staan, dan is "
        "het rapport stilletjes nog op dat jaar")
