"""Placing a webshop order (CR-21, phase 2): the server recomputes every price,
reserves the lines, and one order holds the whole basket (T13, T6's price half,
T7)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app.domains.pricing.api import add_prices
from app.domains.product.api import ProductStatus, add_variant, create_product, set_status
from app.domains.stock.api import available, receive

pytestmark = pytest.mark.ui_agnostisch


def _variant_with_price_and_stock(db, *, name: str, size: str, amount: str, stock: int):
    product = create_product(db, name)
    set_status(db, product.id, ProductStatus.ON_SALE)
    variant = add_variant(db, product.id, size)
    add_prices(
        db,
        product_id=product.id,
        variant_id=variant.id,
        valid_from=date(2026, 1, 1),
        amount=Decimal(amount),
        member_amount=None,
    )
    receive(db, variant.id, quantity=stock)
    return variant


def test_place_order_computes_the_prices_and_reserves_the_lines(db_session, every_module_on):
    """T13/T6: two sizes posted as one order; the total is the server's sum of
    their prices, and both lines are reserved."""
    from app.domains.mdm.api import PaymentMethod
    from app.domains.sales.api import place_order, total_of

    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    variant_l = _variant_with_price_and_stock(
        db_session, name="T-shirt", size="L", amount="17.50", stock=5
    )

    order = place_order(
        db_session,
        person_id=None,
        guest_name="An",
        guest_email="an@example.com",
        guest_mobile="0470000000",
        method=PaymentMethod.TRANSFER,
        items=[(m.id, 2), (variant_l.id, 1)],
        member=False,
    )
    db_session.commit()

    assert len(order.lines) == 2
    assert total_of(order) == Decimal("47.50")
    assert available(db_session, m.id) == 3
    assert available(db_session, variant_l.id) == 4


def test_the_posted_price_is_ignored(db_session, every_module_on):
    """The browser posts ids and quantities only; the price is the server's
    (C5): the total is the price in force, not a number the caller could send."""
    from app.domains.mdm.api import PaymentMethod
    from app.domains.sales.api import place_order, total_of

    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    order = place_order(
        db_session,
        person_id=None,
        guest_name="An",
        guest_email="an@example.com",
        guest_mobile="0470000000",
        method=PaymentMethod.TRANSFER,
        items=[(m.id, 2)],
        member=False,
    )
    db_session.commit()
    assert total_of(order) == Decimal("30.00")
    assert order.lines[0].unit_price == Decimal("15.00")


def test_posting_places_one_order_and_starts_a_transfer(client, db_session, every_module_on):
    """T13/T7: the basket posts as one order; a transfer starts a payment record
    and answers the thank-you page."""
    from app.domains.sales.models import SalesOrder

    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)

    response = client.post(
        "/webshop/bestellen",
        data={
            "variant_id": str(m.id),
            "quantity": "2",
            "contact_name": "An",
            "contact_email": "an@example.com",
            "phone": "0470000000",
            "payment_method": "transfer",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert "/webshop/bedankt?order=" in response.headers["location"]
    order = db_session.query(SalesOrder).first()
    assert order is not None
    assert len(order.lines) == 1
    assert available(db_session, m.id) == 3
