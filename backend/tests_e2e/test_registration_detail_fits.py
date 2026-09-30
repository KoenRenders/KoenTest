"""E2E #1367: the registration detail fits the screen, reading and editing.

Found while building CR-14 phase 3: in edit mode the detail's header puts the
cluster "Verwijderen · Annuleren · Opslaan" next to the name and the contact line,
the row does not wrap, and at 390 px the page scrolled sideways — `scrollWidth` 423
with an address of 21 characters (master CLI's measurement). The contact block did
not shrink either, so a long address alone could push it out.

Measured on the rendered page, at 390 and 1280 px, in read mode and in edit mode,
with a long e-mail address: the document is exactly as wide as the viewport.

Proven red against master `ae660424` (30 September 2026), with this test's address:
390 px in read mode `scrollWidth` 469 (the contact line did not shrink), 390 px in
edit mode 574; both 1280 px cases fitted.
"""

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

LONG_EMAIL = "een.heel.lang.adres.van.een.gezin@example.com"


@pytest.fixture(scope="module")
def setup():
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities import service
    from app.domains.auth.api import make_session_value
    from app.schemas.activity import RegistrationCreate
    from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product

    db = SessionLocal()
    activity, component, product = seed_activity_with_product(db, price="0", is_free=True)
    data = RegistrationCreate(
        contact_name="Lang Adres",
        contact_email=LONG_EMAIL,
        phone="0470000000",
        component_id=component.id,
        items=[{"product_id": product.id, "quantity": 1}],
    )
    registration = service.register(db, activity, data, person_id=None, actor="e2e")
    db.commit()
    out = {"registration": registration.id, "session": make_session_value(SEEDED_ADMIN_EMAIL)}
    db.close()
    return out


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b
        b.close()


@pytest.mark.parametrize("width", [390, 1280])
@pytest.mark.parametrize("mode", ["read", "edit"])
def test_the_detail_is_as_wide_as_the_screen(browser, setup, width, mode):
    context = browser.new_context(base_url=BASE, viewport={"width": width, "height": 900})
    page = context.new_page()
    try:
        login_met_sessie(page, setup["session"])
        page.goto(f"/admin/inschrijvingen/{setup['registration']}")
        pagina_klaar(page)
        assert page.get_by_text(LONG_EMAIL).count() >= 1, "the long address is not on the page"
        if mode == "edit":
            page.get_by_role("button", name="Bewerken").first.click()
            page.get_by_role("button", name="Annuleren").first.wait_for(state="visible")
        wide = page.evaluate(
            """() => ({doc: document.documentElement.scrollWidth, vw: innerWidth,
                out: [...document.querySelectorAll('body *')]
                  .filter(e => e.offsetParent && e.getBoundingClientRect().right > innerWidth + 0.5)
                  .slice(0, 3).map(e => e.tagName + ' ' + Math.round(e.getBoundingClientRect().right))})"""
        )
        assert wide["doc"] == wide["vw"], f"{mode} @{width}: {wide}"
    finally:
        context.close()
