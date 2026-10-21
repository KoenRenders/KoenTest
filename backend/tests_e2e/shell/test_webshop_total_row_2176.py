"""E2E: the order's bottom row fits a phone, and Verkoop's *Annuleren* draws a cancel
icon (#2176).

One open order with a paid total of four digits (the heaviest case), seen by the board
in Verkoop and by the buyer in Mijn aankopen, at 390 and at 1100 px:

- the right edge of the last button stays inside the card's content box (the `p-5`);
- the total's text is on one line;
- the page has no horizontal scroll;
- at 1100 px the total and the buttons stand on one row; at 390 px the buttons stand
  under the total;
- the board's *Annuleren* draws `circle-x`, not `trash-2`.

Proven red (20 October 2026, put back): the row's old classes
(`flex items-center justify-between`) → at 390 px the board's last button ends at 374 px
past a content box ending at 329, and the buyer's total takes two lines;
`lead_icon="trash-2"` → the icon assertion is red.

When `E2E_PRINT_DIR` is set a print of both views at 390 px is taken. The article and
the order are made for this file and stay: the e2e database is fresh per run. The file's
name sorts it after `test_webshop.py` and `test_webshop_product_page.py`, which read the
shop's first row and count its articles; run before them, the extra article turns them red.
"""

from __future__ import annotations

import os
import sys

import pytest
from playwright.sync_api import sync_playwright

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests_e2e.schermen import login_met_sessie, pagina_klaar  # noqa: E402

WEBSHOP_HOST = "http://webshop.localhost:8000"
BUYER = "webshop.lid@example.com"
CIRCLE_X = 'd="m15 9-6 6"'


def _seed() -> int:
    """A paid order of € 1.234,50 by the shop's member, on the shop's tenant."""
    import secrets
    from datetime import date
    from decimal import Decimal

    import app.models  # noqa: F401
    from app.database import SessionLocal
    from app.domains.mdm.api import ContactDetail, PaymentMethod, Person, tenant_codes
    from app.domains.payment.api import PayableType, confirm_manual_payment, get_records_for
    from app.domains.pricing.api import add_prices
    from app.domains.product.models import Product, ProductStatus, ProductVariant
    from app.domains.sales.api import submit_order
    from app.domains.stock.api import receive
    from app.kernel.form_guard import TRUSTED
    from app.kernel.tenancy import current_tenant_id
    from tests.conftest import form_guard_fields

    db = SessionLocal()
    token = current_tenant_id.set(tenant_codes(db)["winkel"])
    try:
        product = Product(name=f"Webshop Duur {secrets.token_hex(3)}", status=ProductStatus.ON_SALE)
        db.add(product)
        db.flush()
        variant = ProductVariant(product_id=product.id, properties=[{"name": "Maat", "value": "M"}])
        db.add(variant)
        db.flush()
        receive(db, variant.id, quantity=1)
        add_prices(
            db,
            product_id=product.id,
            variant_id=variant.id,
            valid_from=date(2026, 1, 1),
            amount=Decimal("1234.50"),
            member_amount=None,
        )
        buyer = (
            db.query(Person)
            .join(ContactDetail, ContactDetail.party_id == Person.party_id)
            .filter(ContactDetail.value == BUYER)
            .one()
        )
        db.commit()
        _checkout, order_id, _key = submit_order(
            db,
            proof=TRUSTED,
            values=form_guard_fields(),
            person_id=buyer.id,
            member=False,
            contact_name="",
            contact_email="",
            phone="",
            method=PaymentMethod.TRANSFER,
            items=[(variant.id, 1)],
        )
        (record,) = get_records_for(db, PayableType.ORDER, order_id)
        confirm_manual_payment(db, record.id, amount_paid=record.amount, actor="e2e@example.com")
        db.commit()
        return order_id
    finally:
        current_tenant_id.reset(token)
        db.close()


@pytest.fixture(scope="module")
def world():
    from app.domains.auth.api import make_session_value
    from tests.conftest import SEEDED_ADMIN_EMAIL

    order_id = _seed()
    with sync_playwright() as pw:
        exe = os.environ.get("E2E_CHROMIUM_PATH")
        browser = pw.chromium.launch(executable_path=exe) if exe else pw.chromium.launch()
        yield {
            "browser": browser,
            "order": order_id,
            "admin": make_session_value(SEEDED_ADMIN_EMAIL),
            "buyer": make_session_value(BUYER),
        }
        browser.close()


_MEASURE = """() => {
  const row = document.querySelector('[data-order-total-row]');
  const card = row.closest('.p-5');
  const pad = parseFloat(getComputedStyle(card).paddingRight);
  const total = row.querySelector('[data-order-total]');
  const buttons = [...row.querySelectorAll('button, a')];
  const last = buttons[buttons.length - 1];
  const t = total.getBoundingClientRect();
  return {
    buttons: buttons.length,
    lastRight: last.getBoundingClientRect().right,
    lastTop: last.getBoundingClientRect().top,
    contentRight: card.getBoundingClientRect().right - pad,
    totalHeight: t.height,
    totalBottom: t.bottom,
    totalTop: t.top,
    lineHeight: parseFloat(getComputedStyle(total).lineHeight),
    scrollWidth: document.documentElement.scrollWidth,
    width: window.innerWidth,
    paths: last.querySelector('svg') ? last.querySelector('svg').innerHTML : '',
  };
}"""


def _print(page, name: str) -> None:
    folder = os.environ.get("E2E_PRINT_DIR")
    if not folder:
        return
    os.makedirs(folder, exist_ok=True)
    page.evaluate("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
    page.screenshot(path=os.path.join(folder, f"{name}-390.png"), caret="initial")


@pytest.mark.parametrize("width", [390, 1100])
@pytest.mark.parametrize("who", ["admin", "buyer"])
def test_the_total_row_fits_and_the_cancel_draws_circle_x(world, who, width):
    path = (
        f"/admin/verkoop/{world['order']}" if who == "admin" else f"/mijn/aankopen/{world['order']}"
    )
    page = world["browser"].new_page(
        base_url=WEBSHOP_HOST, viewport={"width": width, "height": 900}
    )
    try:
        login_met_sessie(page, world[who], WEBSHOP_HOST)
        page.goto(path)
        pagina_klaar(page)
        m = page.evaluate(_MEASURE)
        assert m["buttons"] == (2 if who == "admin" else 1), m
        assert m["lastRight"] <= m["contentRight"] + 0.5, m
        assert m["totalHeight"] <= m["lineHeight"] + 0.5, m
        assert m["scrollWidth"] == m["width"], m
        if width == 390:
            assert m["lastTop"] >= m["totalBottom"], f"the buttons stand under the total: {m}"
        else:
            assert m["lastTop"] < m["totalBottom"], f"one row on a wide screen: {m}"
        if who == "admin":
            assert CIRCLE_X in m["paths"] and 'd="M3 6h18"' not in m["paths"], m["paths"]
            if width == 390:
                _print(page, "bestelling-beheer")
        elif width == 390:
            _print(page, "bestelling-lid")
    finally:
        page.close()
