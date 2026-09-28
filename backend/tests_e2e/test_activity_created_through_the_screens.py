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

Broken on purpose to check this test can go red (run, then restored), one per
admin screen, each an additive change to the route:
  - `activiteit_aanmaken` refuses every request with a 422 → fails at
    "step 1 (Nieuwe activiteit)";
  - `onderdeel_toevoegen` returns the detail without calling `add_component` →
    fails at "step 2 (onderdeel toevoegen)";
  - `product_toevoegen` returns the detail without calling `add_product` →
    fails at "step 3 (product toevoegen)".
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

from tests_e2e.schermen import BASE, htmx_afgerond, login_als_admin  # noqa: E402

PRICE_TYPED = "12,50"  # as a Belgian board member types it
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
            # The editor opens with the name in its own field, not as text.
            expect(page.locator("#aa-detail #name")).to_have_value(name)

        with _step("step 2 (onderdeel toevoegen)"):
            page.get_by_role("button", name="+ Onderdeel").click()
            page.fill("#nc-name", component)
            add_component = page.locator(
                f"form[hx-post='/admin/activiteiten/{activity_id}/onderdelen']"
            )
            with htmx_afgerond(page):
                add_component.get_by_role("button", name="Toevoegen").click()
            product_form = page.locator(
                f"form[hx-post^='/admin/activiteiten/{activity_id}/onderdelen/'][hx-post$='/producten']"
            )
            expect(product_form).to_have_count(1)
            component_id = int(
                re.search(
                    r"/onderdelen/(\d+)/producten", product_form.get_attribute("hx-post")
                ).group(1)
            )
            expect(page.locator("#aa-detail")).to_contain_text(component)

        with _step("step 3 (product toevoegen)"):
            page.get_by_role("button", name="+ Product").click()
            page.fill(f"#pname-{component_id}", product)
            page.fill(f"#pprice-{component_id}", PRICE_TYPED)
            with htmx_afgerond(page):
                product_form.get_by_role("button", name="Toevoegen").click()
            expect(page.locator("#aa-detail")).to_contain_text(product)

        with _step("step 4 (publiek zichtbaar, met product en prijs)"):
            page.goto("/activiteiten")
            register = page.locator(
                f'button[hx-get="/activiteiten/{activity_id}/inschrijven/{component_id}"]'
            )
            expect(register).to_have_count(1)
            register.click()
            form = page.locator(f"#inschrijf-{activity_id}-{component_id}")
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
