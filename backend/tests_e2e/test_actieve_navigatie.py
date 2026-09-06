"""E2E: het actieve menu-item verspringt bij een gebooste navigatie (#714).

Alleen een echte browser kan dit bewijzen. De server had het altijd goed — elke
module bouwt haar nav met het juiste actieve pad — maar `HX-Reselect: #main` haalde
alleen de inhoud uit het antwoord, dus de zijbalk bleef staan met de markering van het
vorige scherm. De fout zat dus niet in het antwoord maar in wat de pagina ermee deed,
en dat is per definitie gedrag in de browser.

Een server-side test hierop zou vandaag al groen zijn geweest en niets bewijzen; die
in `tests/test_actieve_navigatie.py` toetst daarom het mechanisme (de nav komt mee als
out-of-band swap), en deze de uitkomst.
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_als_admin  # noqa: E402


def _ontbreekt(reden: str) -> None:
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
        page.goto("/admin/leden")
        if page.locator("main").count() == 0:
            browser.close()
            pytest.skip("adminsessie niet aanvaard door deze omgeving")
        yield page
        browser.close()


def _actief(page) -> list[str]:
    """De href's die in de zijbalk als actief gemarkeerd staan."""
    return page.eval_on_selector_all(
        "#admin-nav-zijbalk a.bg-white\\/20", "els => els.map(e => e.getAttribute('href'))")


def test_de_markering_volgt_een_geboorde_navigatie(admin_page):
    """Het gemelde geval: klikken naar Activiteiten terwijl Leden opgelicht bleef.

    We navigeren via een KLIK in de zijbalk, niet via `goto()` — een harde navigatie
    laadt de pagina opnieuw en verbergt juist de fout. Het gaat om de gebooste swap.
    """
    admin_page.goto("/admin/leden")
    admin_page.wait_for_selector("#admin-nav-zijbalk")
    assert _actief(admin_page) == ["/admin/leden"], _actief(admin_page)

    admin_page.click('#admin-nav-zijbalk a[href="/admin/activiteiten"]')
    admin_page.wait_for_url("**/admin/activiteiten")
    admin_page.wait_for_timeout(300)

    na = _actief(admin_page)
    assert na == ["/admin/activiteiten"], (
        f"de markering bleef op het vorige scherm staan: {na}")


def test_er_licht_altijd_precies_een_item_op(admin_page):
    """De keerzijde: twee gemarkeerde items is even verwarrend als één verkeerde, en
    dat is wat je krijgt als de oude zijbalk blijft staan naast een nieuwe."""
    admin_page.goto("/admin/leden")
    admin_page.wait_for_selector("#admin-nav-zijbalk")
    admin_page.click('#admin-nav-zijbalk a[href="/admin/betalingen"]')
    admin_page.wait_for_url("**/admin/betalingen")
    admin_page.wait_for_timeout(300)

    assert len(_actief(admin_page)) == 1, _actief(admin_page)
