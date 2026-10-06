"""E2E: a board member who is also a member opens the portal link, signs in with
the code, and lands in the portal — not on the workbench (#1437).

At 390 px, through the screens a person uses: the portal link sends them to the
sign-in page with the way back, the e-mail step, the code step, and the portal.
The code itself cannot come from a mail here, so the test sets the stored code
to a known value after the e-mail step — the same hash the app compares with.

Proven red against master `cbd15865`: there the portal's redirect carried no
`terug`, and the code step landed the ADMIN on `/admin/werkbank`.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, pagina_klaar  # noqa: E402


@pytest.fixture(scope="module")
def board_member():
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.auth.api import User, UserRole
    from tests.conftest import create_test_family

    email = f"bestuur-lid-{secrets.token_hex(3)}@example.com"
    db = SessionLocal()
    try:
        create_test_family(db, email=email)
        user = User(email=email, is_active=True)
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_code="ADMIN"))
        db.commit()
    finally:
        db.close()
    return email


def _set_code(email: str, code: str) -> None:
    """Give the living sign-in token a known code (the mail is not readable here)."""
    from app.database import SessionLocal
    from app.domains.auth.login import _hash_otp
    from app.domains.auth.models import LoginToken

    db = SessionLocal()
    try:
        token = (
            db.query(LoginToken)
            .filter(LoginToken.email == email, LoginToken.used.is_(False))
            .order_by(LoginToken.id.desc())
            .first()
        )
        assert token is not None, "the e-mail step created no sign-in token"
        token.otp_code = _hash_otp(code)
        db.commit()
    finally:
        db.close()


def test_the_portal_link_signs_in_and_comes_back_to_the_portal(board_member):
    with sync_playwright() as p:
        browser = p.chromium.launch()
        page = browser.new_page(viewport={"width": 390, "height": 844})

        page.goto(BASE + "/leden/gezin")
        pagina_klaar(page)
        assert page.url == BASE + "/aanmelden?terug=/leden/gezin", page.url

        page.fill("input[name=email]", board_member)
        page.get_by_role("button", name="Stuur inloginfo").click()
        page.wait_for_selector("input[name=code]")
        _set_code(board_member, "424242")

        page.fill("input[name=code]", "424242")
        page.get_by_role("button", name="Inloggen").click()
        page.wait_for_url(BASE + "/leden/gezin")
        pagina_klaar(page)

        assert page.locator("h1").first.inner_text().strip() == "Mijn gezin"
        assert page.evaluate("document.documentElement.scrollWidth") <= 390
        browser.close()
