"""E2E: a confirmation question on the submitting button really asks (#986).

`ui.btn_primary(confirm=…)` puts `data-confirm` on the button. In an `hx-post`
form htmx names the FORM as the confirming element, so the question on the
button was never read: in the form builder one click on "Importeren" replaced
the whole structure. The repair is in the mechanism (`confirm_host()` in
`_macros.html` also reads the submitting button), so this test drives the
screen where it went wrong.

Only a browser proves it: the server renders the same markup either way.

Broken on purpose: the `submitter` lookup removed from the `htmx:confirm`
handler → no dialog opens, the import request goes out on the first click, and
both tests fail on the missing dialog (measured, 2 failed).
"""
import os
import re
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_als_admin  # noqa: E402

VRAAG = "De volledige opbouw van dit formulier vervangen?"
PAYLOAD = """{"title": "E2E geimporteerd", "status": "draft",
  "fields": [{"field_type": "text", "label": "Vraag uit de import",
              "required": false, "options": []}]}"""


def _admin_email() -> str:
    override = os.environ.get("E2E_ADMIN_EMAIL")
    if override:
        return override
    from tests.conftest import SEEDED_ADMIN_EMAIL

    return SEEDED_ADMIN_EMAIL


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        instance = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield instance
        instance.close()


@pytest.fixture
def importkaart(browser):
    """A fresh form in the builder, with the JSON import open and filled in.

    Yields the page and the list of import requests that left the browser.
    """
    from app.domains.auth.api import make_session_value

    email = _admin_email()
    page = browser.new_page(base_url=BASE)
    login_als_admin(page, email, make_session_value(email))
    page.goto("/admin/formulieren/nieuw")
    page.fill("#f-title", "E2E bevestiging")
    page.locator("form[hx-post='/admin/formulieren'] button[type=submit]").click()
    page.wait_for_url(re.compile(r".*/admin/formulieren/\d+$"), timeout=10_000)
    page.get_by_role("button", name="JSON-import").click()
    page.locator("textarea[name=payload]").fill(PAYLOAD)

    imports = []
    page.on("request", lambda r: imports.append(r.url) if "/json-import" in r.url else None)
    yield page, imports
    page.close()


def test_importeren_vraagt_eerst_en_annuleren_laat_de_opbouw_staan(importkaart):
    page, imports = importkaart
    page.get_by_role("button", name="Importeren (vervangt de opbouw)").click()

    page.get_by_text(VRAAG).wait_for(timeout=3_000)
    page.get_by_role("button", name="Annuleren").click()
    page.wait_for_timeout(500)

    assert imports == [], "the import went out although the user cancelled"
    assert page.get_by_text("Vraag uit de import").count() == 0


def test_bevestigen_voert_de_import_wel_uit(importkaart):
    """The other half: pausing must not swallow the request."""
    page, imports = importkaart
    page.get_by_role("button", name="Importeren (vervangt de opbouw)").click()

    page.get_by_text(VRAAG).wait_for(timeout=3_000)
    page.get_by_role("button", name="Bevestigen").click()

    page.get_by_text("Vraag uit de import").first.wait_for(timeout=5_000)
    assert len(imports) == 1
