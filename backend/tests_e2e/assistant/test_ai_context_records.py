"""E2E #2124: a note's whole life on its own record, in a browser.

The AI-context list opens each item as a record (CR-11 phase 5, track 2, round
3). What a server test cannot show is that the buttons work where a person
clicks them: "+ Notitie" and its form, Bewerken and Opslaan in the action bar,
Zet uit under Acties, and Verwijderen behind its confirmation dialog.
"""

import os
import re
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_afgerond, login_met_sessie, pagina_klaar  # noqa: E402


@pytest.fixture(scope="module")
def page():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        p = b.new_page(viewport={"width": 390, "height": 844})
        login_met_sessie(p, make_session_value(SEEDED_ADMIN_EMAIL), BASE)
        yield p
        b.close()


def _actions(page, label: str) -> None:
    page.locator("[data-actions-trigger]").click()
    page.locator("[data-actions-menu]").get_by_role("menuitem", name=label).click()


def test_a_note_is_made_edited_switched_off_and_deleted_on_its_record(page):
    title = f"Parkeren {secrets.token_hex(3)}"

    page.goto(BASE + "/admin/ai-context?segment=notities")
    pagina_klaar(page)
    page.locator("[data-list-primary] a", has_text="Notitie").click()
    page.wait_for_url("**/admin/ai-context/notities/nieuw")
    pagina_klaar(page)
    page.fill("#note-title", title)
    page.fill("#note-text", "Aan de kerk.")
    with htmx_afgerond(page):
        page.get_by_role("button", name="Opslaan").click()
    page.wait_for_url(re.compile(r".*/admin/ai-context/notities/\d+$"))
    pagina_klaar(page)
    assert page.locator("h1").inner_text() == title
    assert "Aan de kerk." in page.locator("main").inner_text()

    page.get_by_role("link", name="Bewerken").click()
    page.wait_for_url("**?bewerken=1*")
    pagina_klaar(page)
    page.fill("#edit-add", "Aan de kerk en op het plein.")
    with htmx_afgerond(page):
        page.get_by_role("button", name="Opslaan").click()
    page.wait_for_url(re.compile(r".*/admin/ai-context/notities/\d+$"))
    pagina_klaar(page)
    assert "Aan de kerk en op het plein." in page.locator("main").inner_text()

    with htmx_afgerond(page):
        _actions(page, "Zet uit")
    page.wait_for_function("document.querySelector('[data-badges]').innerText.includes('Uit')")
    pagina_klaar(page)

    _actions(page, "Verwijderen")
    ok = page.locator("[data-dialog] [data-dialog-ok]")
    ok.wait_for(state="visible")
    with htmx_afgerond(page):
        ok.click()
    page.wait_for_url("**/admin/ai-context?segment=notities")
    pagina_klaar(page)
    assert title not in page.locator("main").inner_text(), "the deleted note left the list"
