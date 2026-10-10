"""E2E: a refused delete of an article with a movement shows its reason, visibly
(CR-21, AC19/W23).

Measured in a browser because the defect lived between the server and htmx: the
refusal answered 422 with the whole article page, and its banner landed inside
the closed Acties menu at 0 × 0 px — the user pressed "Definitief verwijderen"
and saw the article unchanged, without a word. Since the delete-gate commit the
answer targets the record's message line (`#product-melding`), so the sentence
stands where the user reads it, and it names the alternative (Afgevoerd).

The article with a movement is seeded (`seed_e2e.py`): no screen makes a movement
yet — Voorraadbeheer is the commit after the gate.
"""

import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

DIALOG = "[data-dialog]"
ARTIKEL = "E2E T-shirt met voorraad"


@pytest.fixture(scope="module")
def page():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        p = b.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
        login_met_sessie(p, make_session_value(SEEDED_ADMIN_EMAIL))
        yield p
        b.close()


def test_a_delete_of_an_article_with_movements_shows_why(page):
    page.goto("/admin/producten")
    pagina_klaar(page)
    page.locator("a[href^='/admin/producten/']").filter(has_text=ARTIKEL).first.click()
    pagina_klaar(page)

    page.click("[data-actions-trigger]")
    page.locator("[data-actions-menu] [hx-post$='/verwijderen']").first.click()
    page.locator(f"{DIALOG}:visible").wait_for()
    page.click(f"{DIALOG} [data-dialog-ok]")

    banner = page.locator("#product-melding [role=alert]")
    expect(banner).to_be_visible()
    assert "voorraadbewegingen" in banner.inner_text()
