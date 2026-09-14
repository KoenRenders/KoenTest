"""E2E-golden-flow voor de vergadermodule (CR-09, #258): aanmaken → notuleren.

Waarom een browser en niet de pytest-suite, die dezelfde routes al raakt: de
schermtests bewijzen dat de server het juiste HTML teruggeeft. Wat ze níét kunnen
bewijzen is dat de knoppen in een echte browser iets dóén — en juist dit scherm
leunt zwaar op htmx: elke handeling (aanwezigheid, notitie, punt toevoegen)
vervangt hetzelfde fragment. Precies het soort dode knop dat in #613/#616 door de
serverkant heen glipte.

De flow blijft opzettelijk kort: aanmaken, één aanwezigheid aanvinken, één notitie
typen. Dat raakt de drie mechanismen (redirect na aanmaken, htmx-swap na een POST,
autosave op `change`) zonder de suite traag te maken.
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_als_admin  # noqa: E402


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
    except Exception as exc:  # pragma: no cover - alleen in een kale omgeving
        pytest.skip(f"backend niet importeerbaar voor de sessiewaarde: {exc}")

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE)
        login_als_admin(page, email, make_session_value(email))
        page.goto("/admin/vergaderingen")
        if page.locator("#vg-lijst").count() == 0:
            inhoud = page.content()[:200]
            browser.close()
            pytest.skip(f"adminsessie niet aanvaard door deze omgeving: {inhoud!r}")
        yield page
        browser.close()


def test_een_vergadering_aanmaken_en_notuleren(admin_page):
    """Aanmaken levert een ingevulde agenda; notuleren blijft staan na de swap."""
    page = admin_page
    page.goto("/admin/vergaderingen/nieuw")
    page.fill("#vg-datum", "2026-10-01")
    page.click("button[type=submit]")
    page.wait_for_url("**/admin/vergaderingen/**")

    # De agenda is samengesteld: de vaste secties staan er, met Varia als laatste.
    assert page.locator("h2", has_text="Evaluatie voorbije activiteiten").count() == 1
    assert page.locator("h2", has_text="Volgende activiteiten").count() == 1
    koppen = page.locator("#vg-document h2").all_text_contents()
    assert koppen[-1].strip() == "Varia", koppen

    # Aanwezigheid: één klik, en de knop komt als 'aanwezig' terug uit de swap.
    knoppen = page.locator("#vg-document form[hx-post*='aanwezigheid'] button")
    if knoppen.count() == 0:
        pytest.skip("geen vergaderkring in deze omgeving om aan te vinken")
    naam = knoppen.first.text_content().strip()
    knoppen.first.click()
    page.wait_for_timeout(700)
    aangevinkt = page.locator("#vg-document form[hx-post*='aanwezigheid'] button").first
    assert "bg-green-50" in (aangevinkt.get_attribute("class") or ""), \
        f"'{naam}' kleurde niet als aanwezig na de swap"


def test_een_notitie_overleeft_de_swap(admin_page):
    """Typen in een punt en wegklikken bewaart de notitie — de autosave op
    `change` is het mechanisme waar een verslag op steunt."""
    page = admin_page
    page.goto("/admin/vergaderingen")
    eerste = page.locator("#vg-lijst a[href*='/admin/vergaderingen/']").first
    if eerste.count() == 0:
        pytest.skip("geen vergadering om in te notuleren")
    eerste.click()
    page.wait_for_selector("#vg-document")

    velden = page.locator("#vg-document textarea[name=notes]")
    if velden.count() == 0:
        pytest.skip("deze vergadering heeft geen punten om op te notuleren")
    velden.first.fill("Uitverkocht — 300 tickets.")
    page.locator("#vg-document h2").first.click()  # blur → change → htmx-post
    page.wait_for_timeout(900)

    opnieuw = page.locator("#vg-document textarea[name=notes]").first
    assert "300 tickets" in (opnieuw.input_value() or ""), \
        "de notitie stond niet meer in het veld na de swap"
