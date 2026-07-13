"""E2E golden flows (React-exit 405-e, #405) — playwright-python tegen de
server-rendered site (geen Node meer).

Draait NIET in de gewone pytest-suite (testpaths=tests): vereist een live
backend op E2E_BASE_URL (default http://localhost:8000) met gemigreerde DB en
geseede postcodes. CI start uvicorn en draait `pytest tests_e2e`.
"""
import os
import time

import pytest
from playwright.sync_api import expect, sync_playwright

BASE = os.environ.get("E2E_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="module")
def page():
    with sync_playwright() as pw:
        # E2E_CHROMIUM_PATH: gebruik een vooraf geïnstalleerde Chromium (bv. in
        # een sandbox) i.p.v. de door `playwright install` beheerde download.
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE)
        yield page
        browser.close()


def _vul_hoofdlid(page, email: str):
    page.fill("#m0_first_name", "Test")
    page.fill("#m0_last_name", "Gezin")
    page.fill("#m0_email", email)
    page.fill("#m0_mobile", "0470000000")
    page.fill("#street", "Teststraat")
    page.fill("#house_number", "1")


def test_gezinsregistratie_met_overschrijving(page):
    """Kernflow (#128): gezinsregistratie via Word lid met betaaltype
    overschrijving — raakt Mollie niet, dus stabiel zonder gateway-stub."""
    page.goto("/lid-worden")
    _vul_hoofdlid(page, f"e2e+{int(time.time())}@example.com")
    # Postcode: altijd kiezen uit de dropdown (vaste UI-beslissing).
    page.select_option("#postal_code", index=1)
    page.check('input[name="payment_method"][value="transfer"]')
    page.click('button[type="submit"]')
    expect(page.get_by_text("Je inschrijving is ontvangen")).to_be_visible()


def test_gezinsregistratie_zonder_postcode_geblokkeerd(page):
    """#160: zonder gekozen postcode wordt het formulier niet verstuurd —
    de verplichte dropdown blokkeert de submit."""
    page.goto("/lid-worden")
    _vul_hoofdlid(page, "nopc@example.com")
    page.click('button[type="submit"]')
    # Geen navigatie/succes: de select is invalid en het formulier staat er nog.
    assert page.eval_on_selector("#postal_code", "el => el.checkValidity()") is False
    expect(page.get_by_text("Je inschrijving is ontvangen")).not_to_be_visible()


def test_publieke_kern_bereikbaar(page):
    """Smoke: de publieke kernpagina's renderen server-side."""
    for pad, tekst in (("/", "Raak"), ("/activiteiten", "Activiteiten"),
                       ("/fotos", "Foto's"), ("/berichten", "")):
        resp = page.goto(pad)
        assert resp is not None and resp.ok, pad
        if tekst:
            expect(page.get_by_text(tekst).first).to_be_visible()
