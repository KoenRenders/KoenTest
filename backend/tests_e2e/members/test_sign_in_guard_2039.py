"""E2E: a person can still sign in through the form, with the guard on it (#2039).

The guard drops what comes in less than two seconds after the form was shown, silently,
with the ordinary code step — so a limit that refuses people would thank them all the same
and send nothing. This test types the address at a person's pace (100 ms a key) and then
looks in the database for the token: no token means the guard refused a person.

The other side — a post without the guard's fields, or too fast — is proved on the server
(`test_sign_in_guard_2039.py` in `tests/integration`); a browser test cannot make the page
load slower than two seconds without a sleep.
"""

import os
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, htmx_afgerond, pagina_klaar  # noqa: E402

#: A quick typist's pace, as the other public forms' e2e.
KEY_DELAY_MS = 100


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


def _tokens(email: str) -> int:
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.auth.api import LoginToken

    db = SessionLocal()
    try:
        return db.query(LoginToken).filter_by(email=email).count()
    finally:
        db.close()


def _admin_email() -> str:
    """The address of the seeded admin, as the other browser tests of the meetings read it:
    from the environment, or from the test configuration — never by importing it before the
    app, which would point the database url at the unit-test database."""
    override = os.environ.get("E2E_ADMIN_EMAIL")
    if override:
        return override
    import app.models  # noqa: F401
    from tests.conftest import SEEDED_ADMIN_EMAIL

    return SEEDED_ADMIN_EMAIL


def test_a_person_typing_an_address_gets_the_code(browser):
    SEEDED_ADMIN_EMAIL = _admin_email()

    before = _tokens(SEEDED_ADMIN_EMAIL)
    page = browser.new_page(base_url=BASE, viewport={"width": 390, "height": 844})
    try:
        page.goto("/aanmelden")
        pagina_klaar(page)
        page.locator('input[name="email"]').press_sequentially(
            SEEDED_ADMIN_EMAIL, delay=KEY_DELAY_MS
        )
        with htmx_afgerond(page):
            page.get_by_role("button", name="Stuur inloginfo").click()
        expect(page.locator("[data-code-sent]")).to_be_visible()
        assert _tokens(SEEDED_ADMIN_EMAIL) == before + 1, (
            "the code step came, but no code was stored: the guard refused a person"
        )
    finally:
        page.close()
