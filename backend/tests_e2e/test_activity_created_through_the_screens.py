"""#1269 — an activity is created through the admin screens, end to end.

Every other e2e test makes its activities in the database (`seeded_activities` in
test_golden_flows.py). That is right for tests about public registration, but it
left the first step of the chain untested: if *Nieuwe activiteit*, adding a
component or adding a product broke, the whole suite stayed green. Without an
activity there is no component, without a component no product, and without a
product no registration and no payment.

So this test builds everything through the screens, in the order a board member
does, and then crosses to the public side: the activity is listed, its
registration form shows the product with its price. Afterwards it counts, in a
FRESH database session and not through the request's, exactly one activity, one
component and one product under a name no other test uses — and removes them
again, because the e2e tests share their seed (#1241: a leftover row shifted
another test's first match).

Broken on purpose to check this test can go red (run, then restored), each an
additive change:
  - `activiteit_aanmaken` refuses every request with a 422 → fails at
    "step 1 (Nieuwe activiteit)";
  - since #1559 the component and its product go with the fiche's one save:
    `save_fiche` handing no component to `_save_components` → fails at
    "step 3 (opslaan)".
"""

import os
import re
import sys
import uuid
from contextlib import contextmanager
from datetime import date, timedelta
from decimal import Decimal

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_als_admin, open_registration, pagina_klaar  # noqa: E402

# The price is a number field since #1559: the browser takes the comma of its own
# locale and sends a point, which is what a script has to give it.
PRICE_TYPED = "12.50"
PRICE = Decimal("12.50")
PRICE_SHOWN = "€12,50"  # as the public form renders it


@contextmanager
def _step(label: str):
    """Name the step in any failure, so a red run says which screen broke."""
    try:
        yield
    except Exception as exc:  # assertions and playwright timeouts alike
        raise AssertionError(f"{label}: {exc}") from exc


def _missing(reason: str) -> None:
    if os.environ.get("E2E_SEEDED") == "1":
        pytest.fail(f"e2e seed loaded but: {reason}")
    pytest.skip(reason)


@pytest.fixture(scope="module")
def admin():
    try:
        from app.domains.auth.api import make_session_value
        from tests.conftest import SEEDED_ADMIN_EMAIL

        email = os.environ.get("E2E_ADMIN_EMAIL") or SEEDED_ADMIN_EMAIL
        session_value = make_session_value(email)
    except Exception as exc:  # pragma: no cover - only in a bare environment
        pytest.skip(f"backend not importable for the session value: {exc}")

    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        page = browser.new_page(base_url=BASE, viewport={"width": 1280, "height": 900})
        login_als_admin(page, email, session_value)
        page.goto("/admin/activiteiten/nieuw")
        if page.locator("#name").count() == 0:
            browser.close()
            _missing("admin session not accepted, or the new-activity screen is absent")
        yield page
        browser.close()


def _count_in_a_fresh_session(name: str):
    """Rows under this name, read in a session of our own — not the request's."""
    import app.models  # noqa: F401  load_all_models()
    from app.database import SessionLocal
    from app.domains.activities.api import Activity, ActivityProduct, ActivitySubRegistration

    db = SessionLocal()
    try:
        activities = db.query(Activity).filter(Activity.name == name).all()
        components = (
            db.query(ActivitySubRegistration)
            .filter(ActivitySubRegistration.activity_id.in_([a.id for a in activities]))
            .all()
        )
        products = (
            db.query(ActivityProduct)
            .filter(ActivityProduct.component_id.in_([c.id for c in components]))
            .all()
        )
        return (
            [a.id for a in activities],
            [c.name for c in components],
            [(p.name, p.price, p.is_free, p.is_active) for p in products],
        )
    finally:
        db.close()


def _component_id(activity_id: int) -> int:
    """The one component the save wrote, read in a session of our own."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities.api import ActivitySubRegistration

    db = SessionLocal()
    try:
        return db.query(ActivitySubRegistration).filter_by(activity_id=activity_id).one().id
    finally:
        db.close()


def _remove(name: str) -> None:
    """Take the activity out again through the service, in a session of our own."""
    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.activities import service
    from app.domains.activities.api import Activity

    db = SessionLocal()
    try:
        for activity in db.query(Activity).filter(Activity.name == name).all():
            service.delete_activity(db, activity.id)
        db.commit()
    finally:
        db.close()


def test_an_activity_created_through_the_screens_is_open_for_registration(admin):
    page = admin
    tag = uuid.uuid4().hex[:8]
    name = f"E2E Schermactiviteit {tag}"
    component = f"Onderdeel {tag}"
    product = f"Ticket {tag}"
    try:
        with _step("step 1 (Nieuwe activiteit)"):
            page.goto("/admin/activiteiten/nieuw")
            page.fill("#name", name)
            page.fill("#start_date", (date.today() + timedelta(days=40)).isoformat())
            page.locator("form[hx-post='/admin/activiteiten'] button[type=submit]").first.click()
            page.wait_for_url(re.compile(r"/admin/activiteiten/\d+$"), timeout=10_000)
            activity_id = int(page.url.rstrip("/").rsplit("/", 1)[1])
            # The record opens in its read state (#1558), the name in its own field.
            expect(page.locator('#aa-detail [data-field="name"] [data-value]')).to_have_text(name)

        with _step("step 2 (onderdeel en product, in de pagina)"):
            # Since #1559 the fiche has one save: the component and its product are
            # rows added in the page, and nothing is sent until "Opslaan".
            page.goto(f"/admin/activiteiten/{activity_id}?bewerken=1")
            pagina_klaar(page)
            page.locator("#aa-group-components > div > [data-group-add]").click()
            page.keyboard.type(component)
            row = page.locator("#aa-group-components > [data-group-rows] > [data-group-row]")
            expect(row).to_have_count(1)
            row.locator("[data-repeating-group] [data-group-add]").click()
            page.keyboard.type(product)
            row.locator('[data-repeating-group] input[name$=".price"]').fill(PRICE_TYPED)

        with _step("step 3 (opslaan)"):
            page.click('[data-provisional-bar] button:has-text("Opslaan")')
            page.wait_for_selector('[data-form-flow][data-mode="read"]')
            pagina_klaar(page)
            expect(page.locator("#aa-detail")).to_contain_text(component)
            expect(page.locator("#aa-detail")).to_contain_text(product)
            component_id = _component_id(activity_id)

        with _step("step 4 (publiek zichtbaar, met product en prijs)"):
            page.goto("/activiteiten")
            # CR-14 phase 1: the card links to the registration page.
            register = page.locator(
                f'a[href="/activiteiten/{activity_id}/inschrijven/{component_id}"]'
            )
            expect(register).to_have_count(1)
            open_registration(page, activity_id, component_id)
            form = page.locator("#inschrijf-pagina")
            expect(form).to_contain_text(product)
            expect(form).to_contain_text(PRICE_SHOWN)

        with _step("step 5 (databank, verse sessie)"):
            ids, components, products = _count_in_a_fresh_session(name)
            assert ids == [activity_id], f"activities under this name: {ids}"
            assert components == [component], f"components: {components}"
            assert products == [(product, PRICE, False, True)], f"products: {products}"
    finally:
        _remove(name)

    ids, _, _ = _count_in_a_fresh_session(name)
    assert ids == [], f"the test left its activity behind: {ids}"
