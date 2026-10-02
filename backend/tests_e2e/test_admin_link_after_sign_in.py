"""E2E: a board member opens an admin link while signed out, signs in with the
code, and lands on that page — with its query (#1458).

At 390 px, through the screens a person uses: the admin link sends them to the
sign-in page with the way back, the e-mail step, the code step, and the page
asked for. The code cannot come from a mail here, so the test sets the stored
code to a known value after the e-mail step — as the #1437 e2e does.

Proven red against master `e73da3ff`: there the admin link answered 401 with
the bare JSON body, and the browser stayed on it.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, pagina_klaar  # noqa: E402
from tests_e2e.test_sign_in_returns_to_the_portal import _set_code  # noqa: E402

PAGE = "/admin/leden?q=Peeters&status=actief"


@pytest.fixture(scope="module")
def board_member():
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.auth.api import User, UserRole

    email = f"bestuur-{secrets.token_hex(3)}@example.com"
    db = SessionLocal()
    try:
        user = User(email=email, is_active=True)
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_code="ADMIN"))
        db.commit()
    finally:
        db.close()
    return email


def test_an_admin_link_signs_in_and_comes_back_to_the_page(board_member):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})

        page.goto(BASE + PAGE)
        pagina_klaar(page)
        assert page.url.startswith(BASE + "/aanmelden?terug="), page.url
        assert "Niet aangemeld" not in page.content(), "the bare 401 body, not the sign-in page"

        page.fill("input[name=email]", board_member)
        page.get_by_role("button", name="Stuur inloginfo").click()
        page.wait_for_selector("input[name=code]")
        _set_code(board_member, "585858")

        page.fill("input[name=code]", "585858")
        page.get_by_role("button", name="Aanmelden").click()
        page.wait_for_url(BASE + PAGE)
        pagina_klaar(page)

        assert page.locator("h1").first.inner_text().strip() == "Leden"
        assert page.locator("input[name=q]").first.input_value() == "Peeters"
        assert page.evaluate("document.documentElement.scrollWidth") <= 390
        browser.close()
