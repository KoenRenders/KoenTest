"""E2E: a user is a record page with one save (#2114).

Opened from the list, at 390 and 1 100 px: the row is the way in to the record, the
record reads first, "Bewerken" opens the editor with ONE save, ticking a role and
saving writes exactly that role and answers the record, read again. Nothing scrolls
sideways, and on a phone the bar's Opslaan stands inside the screen.

Broken on purpose (18 October 2026), put back by the reverse edit: the row's link
taken out of `_gu_tabel.html` → red, the row opens nothing.
"""

import os
import secrets
import sys

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402


@pytest.fixture(scope="module")
def setup():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL)
        b.close()


def _new_account(prefix: str) -> tuple[int, str]:
    from app.database import SessionLocal
    from app.domains.auth.api import User, UserRole
    from app.kernel.tenancy import TENANT_MILLEGEM_ID

    email = f"{prefix}-{secrets.token_hex(3)}@example.com"
    db = SessionLocal()
    try:
        user = User(email=email, is_active=True)
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_code="ADMIN", tenant_id=TENANT_MILLEGEM_ID))
        db.commit()
        return user.id, email
    finally:
        db.close()


def _roles(user_id: int) -> set[str]:
    from app.database import SessionLocal
    from app.domains.auth.api import UserRole

    db = SessionLocal()
    try:
        return {
            row.role_code.value for row in db.query(UserRole).filter(UserRole.user_id == user_id)
        }
    finally:
        db.close()


@pytest.mark.parametrize("width", [390, 1100])
def test_open_from_the_list_change_a_role_and_save(setup, width):
    browser, session = setup
    user_id, email = _new_account("rol")
    page = browser.new_page(base_url=BASE, viewport={"width": width, "height": 900})
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    try:
        login_met_sessie(page, session)
        page.goto("/admin/gebruikers?q=" + email)
        pagina_klaar(page)
        page.get_by_role("link", name=email).click()
        expect(page.locator("main h1")).to_have_text(email)
        pagina_klaar(page)
        expect(page.locator("[data-summary-card]")).to_contain_text("Rollen")
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), (
            "scrolls sideways"
        )

        page.get_by_role("link", name="Bewerken").click()
        pagina_klaar(page)
        boekhouding = page.get_by_label("Boekhouding")
        expect(boekhouding).not_to_be_checked()
        boekhouding.check()
        save = page.locator("[data-action-bar] button[data-form-save]")
        box = save.bounding_box()
        assert box and box["x"] >= 0 and box["x"] + box["width"] <= width, (
            f"Opslaan is outside: {box}"
        )
        save.click()
        expect(page.locator("#gu-record [data-form-flow]")).to_have_attribute("data-mode", "read")
        assert _roles(user_id) == {"ADMIN", "FINANCE"}
        assert page.errors == [], f"the screen throws: {page.errors}"
    finally:
        page.close()
