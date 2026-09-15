"""E2E: het zoekveld in de vergaderkring houdt zijn focus (#939).

Koen: *"Als ik 'Kris V' wil toevoegen verspringt het altijd en moet ik opnieuw
klikken en intypen."* De oorzaak is niet te zien in een servertest: htmx verving
het hele blok, dus het invoerveld werd bij elke toetsaanslag opnieuw opgebouwd.
De HTML was telkens correct — alleen stond de cursor er niet meer in.

Alleen een echte browser kan bewijzen dat de focus blijft staan, en dat de tekst
die je typte er nog staat.
"""
import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_als_admin  # noqa: E402


@pytest.fixture(scope="module")
def admin_page():
    try:
        from app.domains.auth.api import make_session_value
        from tests.conftest import SEEDED_ADMIN_EMAIL
    except Exception as exc:  # pragma: no cover - alleen in een kale omgeving
        pytest.skip(f"backend niet importeerbaar: {exc}")

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE)
        login_als_admin(page, SEEDED_ADMIN_EMAIL, make_session_value(SEEDED_ADMIN_EMAIL))
        page.goto("/admin/vergaderingen/kring")
        if page.locator("#vg-kring").count() == 0:
            browser.close()
            pytest.skip("adminsessie niet aanvaard door deze omgeving")
        yield page
        browser.close()


def test_typen_in_het_zoekveld_verliest_de_focus_niet(admin_page):
    page = admin_page
    page.goto("/admin/vergaderingen/kring")
    page.wait_for_selector("#vg-kring")
    veld = page.locator("#vg-kring input[name=q]")
    veld.click()
    veld.type("Kris V", delay=120)
    # Ruim over de 300 ms debounce heen, zodat de swap zeker gebeurd is.
    page.wait_for_timeout(1200)

    assert veld.input_value() == "Kris V", \
        f"de getypte tekst overleefde de swap niet: {veld.input_value()!r}"
    actief = page.evaluate("document.activeElement && document.activeElement.name")
    assert actief == "q", f"de focus sprong weg naar {actief!r}"
