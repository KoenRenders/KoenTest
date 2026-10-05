"""E2E: how a product is settled is one segmented choice (#1608; end state §3.3).

In a browser, because three things only exist there: the segment's width in the
product's row (three whole words must fit a phone, 12 px indented), the price
fields that switch off when the product is not paid for with the registration,
and that what is chosen is what one "Opslaan" stores.

The activity is made for this file and removed again: the e2e tests share their
seed, and an extra activity shifts the lists of the others.

Broken on purpose (5 October 2026): the `:disabled` taken off the price fields →
the price stays enabled at "Gratis"; the `@change` that follows the segment
removed → the same; the segments made equal thirds again (as the kit drew them)
→ "Ter plaatse" breaks over two lines at 1 440 px.
"""

import os
import sys
from decimal import Decimal

import pytest
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import BASE, login_met_sessie, pagina_klaar  # noqa: E402

NAME = "Afrekentest met drie producten"
PRODUCTS = '[data-repeating-group^="p_order."] > [data-group-rows] > [data-group-row]'


def _db():
    import app.main  # noqa: F401  the whole app, so the domain facades import in order
    from app.database import SessionLocal

    return SessionLocal()


def _seed() -> int:
    from app.domains.activities.api import Activity, ActivityProduct, ActivitySubRegistration

    db = _db()
    try:
        activity = Activity(name=NAME)
        db.add(activity)
        db.flush()
        component = ActivitySubRegistration(
            activity_id=activity.id,
            name="Etentje",
            registration_type_code="INDIVIDUAL",
            price=0,
            is_free=True,
            sort_order=0,
        )
        db.add(component)
        db.flush()
        for order, (name, price, free, on_site) in enumerate(
            (
                ("Soep", "5.00", False, False),
                ("Koffie", "3.00", True, False),
                ("Taart", "4.00", False, True),
            )
        ):
            db.add(
                ActivityProduct(
                    component_id=component.id,
                    name=name,
                    price=Decimal(price),
                    is_free=free,
                    pay_on_site=on_site,
                    sort_order=order,
                )
            )
        db.commit()
        return activity.id
    finally:
        db.close()


def _stored(activity_id: int) -> dict:
    from app.domains.activities.api import ActivityProduct, ActivitySubRegistration

    db = _db()
    try:
        rows = (
            db.query(ActivityProduct)
            .join(
                ActivitySubRegistration, ActivitySubRegistration.id == ActivityProduct.component_id
            )
            .filter(ActivitySubRegistration.activity_id == activity_id)
            .all()
        )
        return {p.name: (p.is_free, p.pay_on_site, p.price) for p in rows}
    finally:
        db.close()


@pytest.fixture(scope="module")
def setup():
    from app.domains.activities import service
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    activity_id = _seed()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        b = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield b, make_session_value(SEEDED_ADMIN_EMAIL), activity_id
        b.close()
    db = _db()
    try:
        service.delete_activity(db, activity_id, actor="e2e-1608@example.com")
    finally:
        db.close()


def _page(setup, width: int, edit: bool = True):
    b, session, activity_id = setup
    page = b.new_page(
        base_url=BASE, viewport={"width": width, "height": 844 if width < 768 else 900}
    )
    page.errors = []
    page.on("pageerror", lambda e: page.errors.append(str(e)))
    login_met_sessie(page, session)
    page.goto(f"/admin/activiteiten/{activity_id}" + ("?bewerken=1" if edit else ""))
    pagina_klaar(page)
    return page


_ROWS = """() => [...document.querySelectorAll('[data-repeating-group^="p_order."] > [data-group-rows] > [data-group-row]')].map(row => {
  const group = row.querySelector('[role=radiogroup]'), box = group.getBoundingClientRect();
  const body = row.querySelector('[data-row-body]').getBoundingClientRect();
  const labels = [...group.querySelectorAll('label')];
  return {segments: row.querySelectorAll('[role=radiogroup]').length,
          switches: row.querySelectorAll('input[name$=".is_free"], input[name$=".pay_on_site"]').length,
          words: labels.map(l => l.innerText.trim()),
          cut: labels.some(l => l.scrollWidth > l.clientWidth + 1),
          lines: labels.map(l => { const r = document.createRange(); r.selectNodeContents(l);
                                   return new Set([...r.getClientRects()].filter(b => b.width > 1).map(b => Math.round(b.top))).size; }),
          chosen: (group.querySelector('input:checked') || {}).value,
          width: Math.round(box.width), inside: box.left >= body.left - 0.5 && box.right <= body.right + 0.5,
          body: Math.round(body.width),
          price_off: row.querySelector('input[name$=".price"]').disabled,
          member_off: row.querySelector('input[name$=".member_price"]').disabled}; })"""


@pytest.mark.parametrize(("width", "window"), [(1440, 1440), (390, 390)])
def test_each_product_has_one_segment_that_fits_and_stands_on_its_choice(setup, width, window):
    page = _page(setup, width)
    try:
        rows = page.evaluate(_ROWS)
        print("MEASURE settlement", width, [(r["width"], r["body"], r["lines"]) for r in rows])
        assert len(rows) == 3
        for row in rows:
            assert row["segments"] == 1 and row["switches"] == 0, row
            assert row["words"] == ["Betalend", "Gratis", "Ter plaatse"], "a label was shortened"
            assert not row["cut"] and row["inside"], row
            if width >= 768:
                assert row["lines"] == [1, 1, 1], f"a label broke over two lines: {row}"
            else:
                # In the 207 px a product's row has on a phone today (the handle's
                # gutter and the child group's indent take the rest) "Ter plaatse"
                # may take two lines; it is whole, and nothing is shortened.
                assert max(row["lines"]) <= 2 and row["lines"][:2] == [1, 1], row
        assert [r["chosen"] for r in rows] == ["paid", "free", "on_site"]
        # the price fields are for a paid product only
        assert [(r["price_off"], r["member_off"]) for r in rows] == [
            (False, False),
            (True, True),
            (True, True),
        ]
        assert page.evaluate("document.documentElement.scrollWidth") == window
        assert page.errors == []
    finally:
        page.close()


def test_the_price_fields_follow_the_choice_and_one_opslaan_stores_it(setup):
    _b, _session, activity_id = setup
    page = _page(setup, 1440)
    try:
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        rows = page.locator(PRODUCTS)
        soup, coffee = rows.nth(0), rows.nth(1)
        price = soup.locator('input[name$=".price"]')
        expect(price).to_be_enabled()
        soup.get_by_text("Gratis", exact=True).click()
        expect(price).to_be_disabled()
        expect(soup.locator('input[name$=".member_price"]')).to_be_disabled()
        expect(price).to_have_value("5.00")  # dimmed, not emptied
        soup.get_by_text("Ter plaatse", exact=True).click()
        expect(price).to_be_disabled()
        # the free one becomes a paid one, with a price
        coffee.get_by_text("Betalend", exact=True).click()
        coffee_price = coffee.locator('input[name$=".price"]')
        expect(coffee_price).to_be_enabled()
        coffee_price.fill("3.50")

        page.locator("[data-form-save]").click()
        expect(page.locator("[data-form-flow]")).to_have_attribute("data-mode", "read")
        words = page.locator("[data-product-settlement]").all_inner_texts()
        assert words == ["Ter plaatse", "Betalend", "Ter plaatse"], words
        stored = _stored(activity_id)
        assert stored["Soep"] == (False, True, Decimal("5.00")), "the price was not kept"
        assert stored["Koffie"] == (False, False, Decimal("3.50"))
        assert stored["Taart"] == (False, True, Decimal("4.00"))
        assert page.errors == []
    finally:
        page.close()


def test_a_new_product_starts_as_a_paid_one(setup):
    page = _page(setup, 1440)
    try:
        page.wait_for_function("window.raakRecordForm && window.raakRecordForm.ready()")
        before = page.locator(PRODUCTS).count()
        page.locator('[data-repeating-group^="p_order."] [data-group-add]').first.click()
        new = page.locator(PRODUCTS).nth(before)
        expect(new.locator("[role=radiogroup] input:checked")).to_have_value("paid")
        expect(new.locator('input[name$=".price"]')).to_be_enabled()
        new.get_by_text("Gratis", exact=True).click()
        expect(new.locator('input[name$=".price"]')).to_be_disabled()
    finally:
        page.close()
