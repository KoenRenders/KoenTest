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
    if stock > 0:
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


def _post(client, variant_id, **extra):
    data = {
        "variant_id": str(variant_id),
        "quantity": "1",
        "contact_name": "An",
        "contact_email": "an@example.com",
        "phone": "0470000000",
        "payment_method": "transfer",
        **extra,
    }
    return client.post("/webshop/bestellen", data=data, follow_redirects=False)


def test_a_forged_price_total_or_discount_changes_nothing(client, db_session, every_module_on):
    """K2.1: nothing the browser sends is an amount — a forged price, total or
    discount is ignored, and the stored line carries the server's price."""
    from app.domains.sales.models import SalesOrderLine

    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    response = _post(client, m.id, price="0.01", total="0.01", discount="14.99")
    assert response.status_code == 303
    line = db_session.query(SalesOrderLine).one()
    assert line.unit_price == Decimal("15.00")


def test_an_online_order_that_cannot_start_leaves_nothing(
    client, db_session, monkeypatch, every_module_on
):
    """K2.2: a provider that refuses rolls the whole order back — no order, no
    line, no reservation, no payment record."""
    from app.domains.payment.models import PaymentRecord
    from app.domains.sales.models import SalesOrder, SalesOrderLine
    from app.domains.stock.models import StockReservation

    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)

    def _boom(db, **kwargs):
        raise ValueError("provider down")

    monkeypatch.setattr("app.domains.payment.handlers.create_payment_record", _boom)
    response = _post(client, m.id, payment_method="online")

    assert response.status_code == 502
    assert db_session.query(SalesOrder).count() == 0
    assert db_session.query(SalesOrderLine).count() == 0
    assert db_session.query(StockReservation).count() == 0
    assert db_session.query(PaymentRecord).count() == 0


def test_a_cash_order_is_refused(client, db_session, every_module_on):
    """K5/R14: the buyer pays online or by transfer; cash is refused in words."""
    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    response = _post(client, m.id, payment_method="cash")
    assert response.status_code == 422
    assert "overschrijving" in response.text


def test_a_guest_order_needs_name_email_and_mobile(client, db_session, every_module_on):
    """K6: a guest's order needs the buyer's name, e-mail and mobile."""
    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    for missing in ("contact_name", "contact_email", "phone"):
        data = {
            "variant_id": str(m.id),
            "quantity": "1",
            "contact_name": "An",
            "contact_email": "an@example.com",
            "phone": "0470000000",
            "payment_method": "transfer",
        }
        data[missing] = ""
        response = client.post("/webshop/bestellen", data=data, follow_redirects=False)
        assert response.status_code == 422, missing


@pytest.mark.parametrize("quantity", ["0", "-1", "abc"])
def test_a_bad_quantity_is_a_refusal_not_a_500(client, db_session, every_module_on, quantity):
    """K2.3: a quantity of zero, negative or not a number is a 422 with a
    sentence, not a 500."""
    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    response = _post(client, m.id, quantity=quantity)
    assert response.status_code == 422


def test_a_sold_out_size_is_refused_in_words(client, db_session, every_module_on):
    """K2.3: a size without stock is refused with the sentence."""
    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=0)
    response = _post(client, m.id)
    assert response.status_code == 422
    assert "voorraad" in response.text


def test_the_last_piece_goes_to_one_buyer_only(every_module_on):
    """K2.4: two orders for the last unit on two committed connections — one is
    placed, one is refused, nothing half-reserved."""
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    from app.database import SessionLocal
    from app.domains.mdm.api import PaymentMethod
    from app.domains.sales.api import place_order
    from app.domains.sales.models import SalesError

    seed = SessionLocal()
    try:
        variant = _variant_with_price_and_stock(
            seed, name="T-shirt", size="M", amount="15.00", stock=1
        )
        variant_id = variant.id
        seed.commit()
    finally:
        seed.close()

    ready = threading.Event()
    outcomes: dict[str, str] = {}

    def _items():
        return [(variant_id, 1)]

    def _place(name, leads):
        db = SessionLocal()
        try:
            if leads:
                place_order(
                    db,
                    person_id=None,
                    guest_name=name,
                    guest_email=f"{name}@x.be",
                    guest_mobile="0470000000",
                    method=PaymentMethod.TRANSFER,
                    items=_items(),
                    member=False,
                )
                ready.set()
                time.sleep(0.6)
                db.commit()
                outcomes[name] = "placed"
            else:
                assert ready.wait(timeout=10)
                try:
                    place_order(
                        db,
                        person_id=None,
                        guest_name=name,
                        guest_email=f"{name}@x.be",
                        guest_mobile="0470000000",
                        method=PaymentMethod.TRANSFER,
                        items=_items(),
                        member=False,
                    )
                except SalesError:
                    db.rollback()
                    outcomes[name] = "refused"
                    return
                db.commit()
                outcomes[name] = "placed"
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        a = pool.submit(_place, "first", True)
        b = pool.submit(_place, "second", False)
        a.result()
        b.result()

    assert outcomes == {"first": "placed", "second": "refused"}

    _clean(variant_id)


def _clean(variant_id: int) -> None:
    """Remove what a two-connection test leaves behind, so the stock tests' own
    two-connection tests still see a fresh database (their location, a made-up
    variant, nothing committed)."""
    from app.database import SessionLocal
    from app.domains.pricing.models import Price
    from app.domains.product.models import Product, ProductVariant
    from app.domains.sales.models import SalesOrder, SalesOrderLine
    from app.domains.stock.models import StockLocation, StockMovement, StockReservation

    db = SessionLocal()
    try:
        variant = db.get(ProductVariant, variant_id)
        product_id = variant.product_id if variant is not None else None
        db.query(SalesOrderLine).filter(SalesOrderLine.variant_id == variant_id).delete(
            synchronize_session=False
        )
        db.query(SalesOrder).delete(synchronize_session=False)
        db.query(StockReservation).filter(StockReservation.variant_id == variant_id).delete(
            synchronize_session=False
        )
        db.query(StockMovement).filter(StockMovement.variant_id == variant_id).delete(
            synchronize_session=False
        )
        if product_id is not None:
            db.query(Price).filter(Price.product_id == product_id).delete(synchronize_session=False)
            db.query(ProductVariant).filter(ProductVariant.id == variant_id).delete(
                synchronize_session=False
            )
            db.query(Product).filter(Product.id == product_id).delete(synchronize_session=False)
        db.query(StockLocation).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_a_strangers_order_is_the_same_404_as_a_missing_one(client, db_session, every_module_on):
    """K2.5: another person's order id and a missing id are the same 404."""
    from app.domains.mdm.api import PaymentMethod
    from app.domains.sales.api import place_order
    from tests.conftest import create_test_family

    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    owner_family = create_test_family(db_session, email="eigenaar@example.com")
    create_test_family(db_session, email="vreemde@example.com")
    order = place_order(
        db_session,
        person_id=owner_family[1].id,
        guest_name="",
        guest_email="",
        guest_mobile="",
        method=PaymentMethod.TRANSFER,
        items=[(m.id, 1)],
        member=False,
    )
    db_session.commit()

    from app.domains.auth.api import SESSION_COOKIE, make_session_value

    client.cookies.set(SESSION_COOKIE, make_session_value("vreemde@example.com"))
    assert client.get(f"/mijn/aankopen/{order.id}").status_code == 404
    assert client.get("/mijn/aankopen/99999999").status_code == 404
