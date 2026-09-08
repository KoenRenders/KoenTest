"""E2E: het mobiele menu klapt niet open na een gebooste navigatie (#737).

Dezelfde val als #726, maar op een plek waar niemand van ons kijkt: de menu's zijn
`md:hidden`, dus je ziet ze alleen op een telefoon.

**Gemeten vóór de fix**, in een venster van 390 px:

    [na laden]                #site-nav-mobiel: zichtbaar=False style='display: none;'
    [na gebooste navigatie]   #site-nav-mobiel: zichtbaar=True  style=None

Het style-attribuut verdwijnt en het menu staat open. De oorzaak is die uit #726:
`style` staat in htmx' `attributesToSettle`, dus een element met een `id` krijgt na
de settle-vertraging de attributen van het serverantwoord terug — en daar stond geen
style, dus htmx wist precies wat Alpine er net op had gezet. Bij een gebooste
navigatie worden deze twee containers out-of-band meegeswapt (#714/#718), dus dat
gebeurt bij élke klik in het menu.

De tweede assert per test is de tegenproef: het menu moet nog wél opengaan met de
☰-knop. Zonder haar staat de test ook groen als je het menu hebt dichtgemetseld in
plaats van gerepareerd — en dan is de navigatie op een telefoon onbereikbaar.

Kapotgemaakt om te controleren dat deze tests rood kunnen worden: `style="display:
none"` weer weggehaald uit de betreffende container → de eerste assert valt om, de
tegenproef blijft groen.
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie  # noqa: E402

# Smal genoeg voor `md:hidden`: onder de md-breekpunt van 768 px.
TELEFOON = {"width": 390, "height": 800}


@pytest.fixture(scope="module")
def telefoon_page():
    try:
        from app.domains.auth.api import make_session_value
        from tests.conftest import SEEDED_ADMIN_EMAIL

        email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
    except Exception as exc:  # pragma: no cover - alleen in een kale omgeving
        pytest.skip(f"backend niet importeerbaar voor de sessiewaarde: {exc}")

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE, viewport=TELEFOON)
        login_met_sessie(page, make_session_value(email))
        yield page
        browser.close()


def _boost_naar(page, selector: str) -> None:
    """Klik een link in de brede navigatie — die staat in de DOM maar is op deze
    breedte verborgen, dus via de DOM en niet via een gebruikersklik."""
    page.evaluate(f"document.querySelector({selector!r})?.click()")
    page.wait_for_timeout(1200)


def test_het_publieke_menu_blijft_dicht_na_een_gebooste_navigatie(telefoon_page):
    page = telefoon_page
    page.goto("/")
    page.wait_for_timeout(400)
    menu = page.locator("#site-nav-mobiel")
    assert not menu.is_visible(), "het menu stond bij het laden al open"

    _boost_naar(page, '#site-nav-breed a[href="/fotos"]')

    assert not menu.is_visible(), (
        "het mobiele menu klapt open na elke navigatie — htmx' settle heeft de "
        "display:none van Alpine gewist (#737)")

    page.get_by_role("button", name="Menu").click()
    page.wait_for_timeout(300)
    assert menu.is_visible(), "het menu gaat niet meer open met de ☰-knop"


def test_het_beheermenu_blijft_dicht_na_een_gebooste_navigatie(telefoon_page):
    page = telefoon_page
    page.goto("/admin/leden")
    page.wait_for_timeout(500)
    menu = page.locator("#admin-nav-mobiel")
    assert not menu.is_visible(), "het menu stond bij het laden al open"

    _boost_naar(page, '#admin-nav-zijbalk a[href="/admin/activiteiten"]')

    assert not menu.is_visible(), (
        "het mobiele beheermenu klapt open na elke navigatie (#737)")

    page.get_by_role("button", name="Menu").click()
    page.wait_for_timeout(300)
    assert menu.is_visible(), "het menu gaat niet meer open met de ☰-knop"
