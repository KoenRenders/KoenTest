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
    db.commit()
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

    assert response.status_code == 200
    assert "/webshop/bedankt?order=" in response.headers["HX-Redirect"]
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


def _committed_variant(stock: int) -> int:
    """A variant with a price and stock, committed on its own connection so a
    later `db_session` rollback in the door does not take the seed with it."""
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        variant = _variant_with_price_and_stock(
            db, name="T-shirt", size="M", amount="15.00", stock=stock
        )
        variant_id = variant.id
        db.commit()
        return variant_id
    finally:
        db.close()


def _cleanup_variant(variant_id: int) -> None:
    """Delete a committed seed variant and everything it made, so the shared test
    database stays clean for the tests after it."""
    from app.database import SessionLocal
    from app.domains.pricing.models import Price
    from app.domains.product.models import Product, ProductVariant
    from app.domains.stock.models import StockLocation, StockMovement, StockReservation

    db = SessionLocal()
    try:
        variant = db.get(ProductVariant, variant_id)
        product_id = variant.product_id if variant is not None else None
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
        if db.query(StockMovement).count() == 0:
            db.query(StockLocation).delete(synchronize_session=False)
        db.commit()
    finally:
        db.close()


def test_a_forged_price_total_or_discount_changes_nothing(client, db_session, every_module_on):
    """K2.1: nothing the browser sends is an amount — a forged price, total or
    discount is ignored, and the stored line and the payment carry the server's."""
    from app.domains.payment.models import PaymentRecord
    from app.domains.sales.models import SalesOrderLine

    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    response = _post(client, m.id, price="0.01", total="0.01", discount="14.99")
    assert response.status_code == 200
    line = db_session.query(SalesOrderLine).one()
    assert line.unit_price == Decimal("15.00")
    record = db_session.query(PaymentRecord).one()
    assert record.amount == Decimal("15.00")


def test_an_online_order_that_cannot_start_leaves_nothing(
    client, db_session, monkeypatch, every_module_on
):
    """K2.2: a provider that refuses rolls the whole order back — no order, no
    line, no reservation, no payment record, no event, the stock untouched."""
    from app.domains.payment.models import PaymentRecord
    from app.domains.sales.models import SalesOrder, SalesOrderLine
    from app.domains.stock.models import StockReservation

    variant_id = _committed_variant(stock=5)

    def _boom(db, **kwargs):
        raise ValueError("provider down")

    published = []
    monkeypatch.setattr("app.domains.payment.handlers.create_payment_record", _boom)
    monkeypatch.setattr("app.kernel.events.publish", lambda event, db: published.append(event))
    try:
        response = _post(client, variant_id, payment_method="online")

        assert response.status_code == 502
        assert db_session.query(SalesOrder).count() == 0
        assert db_session.query(SalesOrderLine).count() == 0
        assert db_session.query(StockReservation).count() == 0
        assert db_session.query(PaymentRecord).count() == 0
        assert published == []
        assert available(db_session, variant_id) == 5
    finally:
        _cleanup_variant(variant_id)


def test_a_provider_that_cannot_be_reached_is_the_same_502(
    client, db_session, monkeypatch, every_module_on
):
    """L1: a timeout or a refused connection (`httpx.HTTPError`) ends the same way
    as a provider's refusal — nothing placed, the buyer told."""
    import httpx

    from app.domains.payment.models import PaymentRecord
    from app.domains.sales.models import SalesOrder

    variant_id = _committed_variant(stock=5)

    def _boom(db, **kwargs):
        raise httpx.ConnectTimeout("no answer")

    monkeypatch.setattr("app.domains.payment.handlers.create_payment_record", _boom)
    try:
        response = _post(client, variant_id, payment_method="online")

        assert response.status_code == 502
        assert db_session.query(SalesOrder).count() == 0
        assert db_session.query(PaymentRecord).count() == 0
    finally:
        _cleanup_variant(variant_id)


def test_a_cash_order_is_refused(client, db_session, every_module_on):
    """K5/R14: the buyer pays online or by transfer; cash is refused in words."""
    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    response = _post(client, m.id, payment_method="cash")
    assert response.status_code == 422
    assert "overschrijving" in response.text


def test_a_guest_order_needs_name_email_and_mobile(client, db_session, every_module_on):
    """K6: a guest's order needs the buyer's name, e-mail and mobile, each
    refused in words, on the order's own `check()`."""
    variant_id = _committed_variant(stock=5)
    try:
        for missing, sentence in (
            ("contact_name", "naam"),
            ("contact_email", "e-mailadres"),
            ("phone", "mobiele"),
        ):
            data = {
                "variant_id": str(variant_id),
                "quantity": "1",
                "contact_name": "An",
                "contact_email": "an@example.com",
                "phone": "0470000000",
                "payment_method": "transfer",
            }
            data[missing] = ""
            response = client.post("/webshop/bestellen", data=data, follow_redirects=False)
            assert response.status_code == 422, missing
            assert sentence in response.text, missing
    finally:
        _cleanup_variant(variant_id)


@pytest.mark.parametrize("quantity", ["0", "-1", "abc"])
def test_a_bad_quantity_is_a_refusal_not_a_500(client, db_session, every_module_on, quantity):
    """K2.3: a quantity of zero, negative or not a number is a 422 with a
    sentence, not a 500."""
    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    response = _post(client, m.id, quantity=quantity)
    assert response.status_code == 422
    assert "Ongeldig aantal" in response.text


def test_a_quantity_over_the_limit_is_refused(client, db_session, every_module_on):
    """K2.3: a quantity over the tenant's maximum is refused in words."""
    from app.kernel.tenant_config import tenant_max_item_quantity

    m = _variant_with_price_and_stock(
        db_session, name="T-shirt", size="M", amount="15.00", stock=5000
    )
    over = tenant_max_item_quantity(db_session) + 1
    response = _post(client, m.id, quantity=str(over))
    assert response.status_code == 422
    assert "Ongeldig aantal" in response.text


def test_a_sold_out_size_is_refused_in_words(client, db_session, every_module_on):
    """K2.3: a size without stock is refused with the sentence."""
    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=0)
    response = _post(client, m.id)
    assert response.status_code == 422
    assert "voorraad" in response.text


def test_a_variant_posted_twice_is_one_line(client, db_session, every_module_on):
    """N3: the same variant posted twice is summed to one line — read through the
    door, so a door that stopped calling `_parse_items` turns this red."""
    from app.domains.sales.models import SalesOrderLine

    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    body = (
        f"variant_id={m.id}&variant_id={m.id}&quantity=1&quantity=2"
        "&contact_name=An&contact_email=an@example.com&phone=0470000000&payment_method=transfer"
    )
    response = client.post(
        "/webshop/bestellen",
        content=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    line = db_session.query(SalesOrderLine).one()
    assert line.quantity == 3


def test_lists_that_do_not_line_up_are_refused(client, db_session, every_module_on):
    """N3: two posted lists of different length are refused through the door, not
    silently zipped."""
    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    body = (
        f"variant_id={m.id}&quantity=1&quantity=2"
        "&contact_name=An&contact_email=an@example.com&phone=0470000000&payment_method=transfer"
    )
    response = client.post(
        "/webshop/bestellen",
        content=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert response.status_code == 422
    assert "Ongeldig aantal" in response.text


def test_a_non_numeric_variant_id_is_refused(client, db_session, every_module_on):
    """N3: a variant id that is not a number is a refusal, not a 500."""
    response = _post(client, "abc")
    assert response.status_code == 422


def test_the_basket_page_shows_the_servers_price(client, db_session, every_module_on):
    """N3: the basket page carries the server's price — the post holds no amount."""
    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    response = client.post(
        "/webshop/mandje",
        data={"variant_id": str(m.id), "quantity": "2"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "T-shirt" in response.text
    assert "15,00" in response.text


def test_an_empty_basket_shows_the_empty_state(client, db_session, every_module_on):
    """N3: an empty post shows the empty state, in the shell."""
    response = client.post("/webshop/mandje", data={}, follow_redirects=False)
    assert response.status_code == 200
    assert "Je mandje is leeg" in response.text


def test_the_thank_you_page_answers_its_own_path(client, db_session, every_module_on):
    """P1's companion: `/webshop/bedankt` must win over `/webshop/{product_id}` —
    the parameter route registered after it used to swallow "bedankt" as a product
    id and answer a 422 int-parsing error instead of the thank-you page."""
    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    placed = _post(client, m.id)
    redirect = placed.headers["HX-Redirect"]
    assert "/webshop/bedankt?order=" in redirect

    page = client.get(redirect)
    assert page.status_code == 200
    assert "Bedankt" in page.text


def test_the_thank_you_page_without_an_order_goes_to_the_shop(client, every_module_on):
    """A bare `/webshop/bedankt` (no order) sends the visitor to the shop, not
    FastAPI's raw JSON 422."""
    response = client.get("/webshop/bedankt", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/webshop"


def test_a_quantity_below_one_is_refused_on_the_basket_page(client, db_session, every_module_on):
    """N6: the basket page refuses a quantity below 1, as placing does — in the
    service, so neither door is the only place the rule holds."""
    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    response = client.post(
        "/webshop/mandje",
        data={"variant_id": str(m.id), "quantity": "0"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "Ongeldig aantal" in response.text


def test_a_gone_line_stays_in_the_basket_marked(client, db_session, every_module_on):
    """Koen's "ja op beide": an article no longer offered stays on its own line
    with its sentence — the basket is not refused, the line is marked."""
    from app.domains.product.api import ProductStatus, set_status

    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    set_status(db_session, m.product_id, ProductStatus.DISCONTINUED)
    db_session.commit()

    response = client.post(
        "/webshop/mandje",
        data={"variant_id": str(m.id), "quantity": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "wordt niet meer aangeboden" in response.text
    assert "Je mandje is leeg" not in response.text


def test_a_sold_out_line_stays_in_the_basket_marked(client, db_session, every_module_on):
    """Koen's "ja op beide": a size without enough stock stays on its own line
    with its sentence ("Nog … op voorraad"), not a refusal of the whole basket."""
    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=1)
    response = client.post(
        "/webshop/mandje",
        data={"variant_id": str(m.id), "quantity": "2"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "Nog 1 op voorraad" in response.text


def test_the_total_counts_only_the_orderable_lines(client, db_session, every_module_on):
    """A basket with a gone line and an orderable line totals only the orderable
    one, and both lines stand on the page."""
    from app.domains.product.api import ProductStatus, set_status

    gone = _variant_with_price_and_stock(db_session, name="Weg", size="M", amount="10.00", stock=5)
    ok = _variant_with_price_and_stock(db_session, name="Blijft", size="L", amount="15.00", stock=5)
    set_status(db_session, gone.product_id, ProductStatus.DISCONTINUED)
    db_session.commit()

    response = client.post(
        "/webshop/mandje",
        content=f"variant_id={gone.id}&variant_id={ok.id}&quantity=1&quantity=1",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    assert "wordt niet meer aangeboden" in response.text
    assert "Blijft" in response.text
    assert "15,00" in response.text
    assert "25,00" not in response.text


def test_a_pre_order_article_without_stock_stays_orderable(client, db_session, every_module_on):
    """Q1: an article "Op bestelling" (window open, no end, stock 0) is orderable
    on the basket page and placed — the basket and the order ask the same rule, so
    the basket cannot mark a line the order would accept."""
    from app.domains.product.api import add_variant, create_product, set_status

    product = create_product(db_session, "T-shirt")
    set_status(db_session, product.id, ProductStatus.ON_SALE)
    product.pre_order = True
    variant = add_variant(db_session, product.id, "M")
    add_prices(
        db_session,
        product_id=product.id,
        variant_id=variant.id,
        valid_from=date(2026, 1, 1),
        amount=Decimal("15.00"),
        member_amount=None,
    )
    db_session.commit()

    basket = client.post(
        "/webshop/mandje",
        data={"variant_id": str(variant.id), "quantity": "2"},
        follow_redirects=False,
    )
    assert basket.status_code == 200
    assert "Nog 0 op voorraad" not in basket.text

    placed = _post(client, variant.id, quantity="2")
    assert placed.status_code == 200
    assert "HX-Redirect" in placed.headers


def test_a_short_line_keeps_its_stepper_and_a_gone_line_does_not(
    client, db_session, every_module_on
):
    """Q2: a line that is only too many (over stock) keeps its stepper, bounded by
    what can be ordered; a line no longer offered keeps only "Verwijderen"."""
    from app.domains.product.api import ProductStatus, set_status

    short = _variant_with_price_and_stock(
        db_session, name="Krap", size="M", amount="15.00", stock=1
    )
    gone = _variant_with_price_and_stock(db_session, name="Weg", size="L", amount="10.00", stock=5)
    set_status(db_session, gone.product_id, ProductStatus.DISCONTINUED)
    db_session.commit()

    response = client.post(
        "/webshop/mandje",
        content=f"variant_id={short.id}&variant_id={gone.id}&quantity=2&quantity=1",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        follow_redirects=False,
    )
    assert response.status_code == 200
    # the short line keeps its stepper (bounded to the stock), the gone one does not
    assert f'data-line-quantity data-variant-id="{short.id}"' in response.text
    assert f'data-line-quantity data-variant-id="{gone.id}"' not in response.text


def test_bestellen_refuses_a_gone_line_posted_anyway(client, db_session, every_module_on):
    """The server is the guard: a gone line posted straight to `/webshop/bestellen`
    is refused — the browser is not the only thing that keeps it out."""
    from app.domains.product.api import ProductStatus, set_status

    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    set_status(db_session, m.product_id, ProductStatus.DISCONTINUED)
    db_session.commit()

    response = _post(client, m.id)
    assert response.status_code == 422
    assert "wordt niet meer aangeboden" in response.text


@pytest.mark.xdist_group("sales_order_placing")
def test_the_last_piece_goes_to_one_buyer_only(every_module_on):
    """K2.4: two orders for the last unit on two committed connections — one is
    placed, one is refused, nothing half-reserved.

    The second buyer calls `place_order` only after the first signalled, and is
    "refused" only on `SalesError` — never by a rollback of its own, so without
    the lock both place and the test is red. Proven red once: taken `_acquire_lock`
    out of `stock.service.reserve`, both threads commit and `outcomes` becomes
    {"first": "placed", "second": "placed"}, so the outcome assertion fails."""
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    from app.database import SessionLocal
    from app.domains.mdm.api import PaymentMethod
    from app.domains.sales.api import place_order
    from app.domains.sales.models import SalesError, SalesOrder, SalesOrderLine
    from app.domains.stock.models import StockLocation, StockReservation

    seed = SessionLocal()
    try:
        variant = _variant_with_price_and_stock(
            seed, name="T-shirt", size="M", amount="15.00", stock=1
        )
        variant_id = variant.id
        location_id = seed.query(StockLocation).first().id
        seed.commit()
    finally:
        seed.close()

    ready = threading.Event()
    outcomes: dict[str, str] = {}
    order_id: int | None = None

    def _items():
        return [(variant_id, 1)]

    def _place(name, leads):
        nonlocal order_id
        db = SessionLocal()
        try:
            if leads:
                order = place_order(
                    db,
                    person_id=None,
                    guest_name=name,
                    guest_email=f"{name}@example.com",
                    guest_mobile="0470000000",
                    method=PaymentMethod.TRANSFER,
                    items=_items(),
                    member=False,
                )
                order_id = order.id
                ready.set()
                time.sleep(0.6)
                db.commit()
                outcomes[name] = "placed"
            else:
                assert ready.wait(timeout=10)
                try:
                    order = place_order(
                        db,
                        person_id=None,
                        guest_name=name,
                        guest_email=f"{name}@example.com",
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

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            a = pool.submit(_place, "first", True)
            b = pool.submit(_place, "second", False)
            a.result()
            b.result()

        assert outcomes == {"first": "placed", "second": "refused"}
        db = SessionLocal()
        try:
            assert db.query(SalesOrder).count() == 1
            assert db.query(SalesOrderLine).count() == 1
            assert db.query(StockReservation).count() == 1
        finally:
            db.close()
    finally:
        _clean(variant_id, order_id, location_id)


def _clean(variant_id: int, order_id: int | None, location_id: int) -> None:
    """Remove exactly what this test made, in a finally — never a broad delete,
    so a red assertion still leaves the database clean for the tests after it."""
    from app.database import SessionLocal
    from app.domains.pricing.models import Price
    from app.domains.product.models import Product, ProductVariant
    from app.domains.sales.models import SalesOrder, SalesOrderLine
    from app.domains.stock.models import StockLocation, StockMovement, StockReservation

    db = SessionLocal()
    try:
        variant = db.get(ProductVariant, variant_id)
        product_id = variant.product_id if variant is not None else None
        if order_id is not None:
            db.query(SalesOrderLine).filter(SalesOrderLine.order_id == order_id).delete(
                synchronize_session=False
            )
            db.query(SalesOrder).filter(SalesOrder.id == order_id).delete(synchronize_session=False)
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
        db.query(StockLocation).filter(StockLocation.id == location_id).delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


def test_a_strangers_order_is_the_same_404_as_a_missing_one(client, db_session, every_module_on):
    """K2.5: the owner and a member of his household open the order; a stranger's
    id and a missing id are the same 404, with the same body."""
    from app.domains.auth.api import SESSION_COOKIE, make_session_value
    from app.domains.mdm.api import ContactDetail, MemberPerson, PaymentMethod
    from app.domains.sales.api import place_order
    from tests.conftest import create_test_family, create_test_person

    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    owner_member, owner_person = create_test_family(db_session, email="eigenaar@example.com")
    partner = create_test_person(db_session)
    db_session.add(
        MemberPerson(member_id=owner_member.id, person_id=partner.id, relation_type="PARTNER")
    )
    db_session.add(
        ContactDetail(person_id=partner.id, contact_type_code="EMAIL", value="partner@example.com")
    )
    create_test_family(db_session, email="vreemde@example.com")
    order = place_order(
        db_session,
        person_id=owner_person.id,
        guest_name="",
        guest_email="",
        guest_mobile="",
        method=PaymentMethod.TRANSFER,
        items=[(m.id, 1)],
        member=False,
    )
    db_session.commit()

    client.cookies.set(SESSION_COOKIE, make_session_value("eigenaar@example.com"))
    assert client.get(f"/mijn/aankopen/{order.id}").status_code == 200
    client.cookies.set(SESSION_COOKIE, make_session_value("partner@example.com"))
    assert client.get(f"/mijn/aankopen/{order.id}").status_code == 200

    client.cookies.set(SESSION_COOKIE, make_session_value("vreemde@example.com"))
    stranger = client.get(f"/mijn/aankopen/{order.id}")
    missing = client.get("/mijn/aankopen/99999999")
    assert stranger.status_code == 404
    assert missing.status_code == 404
    assert stranger.text == missing.text


def test_delivering_a_line_marks_it_and_lowers_the_stock(db_session, every_module_on):
    """F6/R21: delivering one line sets `delivered_at` and the stock goes down by
    the line's quantity."""
    from app.domains.mdm.api import PaymentMethod
    from app.domains.sales.api import deliver_line, place_order
    from app.domains.stock.api import available

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

    deliver_line(db_session, order.id, order.lines[0].id, actor="beheerder@example.com")
    db_session.refresh(order)
    assert order.lines[0].delivered_at is not None
    assert available(db_session, m.id) == 3


def test_cancelling_frees_the_stock_and_leaves_the_lists(db_session, every_module_on):
    """F8/R22: cancelling soft-deletes the order (it leaves the lists) and the
    reservation frees the stock."""
    from app.domains.mdm.api import PaymentMethod
    from app.domains.sales.api import cancel_order, get_order, place_order
    from app.domains.stock.api import available

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

    cancel_order(db_session, order.id, actor="beheerder@example.com")
    assert get_order(db_session, order.id) is None
    assert available(db_session, m.id) == 5


def test_a_delivered_order_cannot_be_cancelled(db_session, every_module_on):
    """F8: once a line is delivered the whole order can no longer be cancelled."""
    import pytest

    from app.domains.mdm.api import PaymentMethod
    from app.domains.sales.api import SalesError, cancel_order, deliver_line, place_order

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
    deliver_line(db_session, order.id, order.lines[0].id, actor="beheerder@example.com")

    with pytest.raises(SalesError):
        cancel_order(db_session, order.id, actor="beheerder@example.com")


def test_a_line_that_waits_for_the_supplier_is_refused_not_a_500(
    client, db_session, every_module_on
):
    """A1: delivering a line that waits for the supplier (an uncovered "Op
    bestelling" reservation) is a refusal through the route — a 422, never a 500."""
    from app.domains.mdm.api import PaymentMethod
    from app.domains.product.api import add_variant, create_product, set_status
    from app.domains.sales.api import place_order
    from tests.conftest import board_session

    product = create_product(db_session, "T-shirt")
    set_status(db_session, product.id, ProductStatus.ON_SALE)
    product.pre_order = True
    variant = add_variant(db_session, product.id, "M")
    add_prices(
        db_session,
        product_id=product.id,
        variant_id=variant.id,
        valid_from=date(2026, 1, 1),
        amount=Decimal("15.00"),
        member_amount=None,
    )
    db_session.commit()

    order = place_order(
        db_session,
        person_id=None,
        guest_name="An",
        guest_email="an@example.com",
        guest_mobile="0470000000",
        method=PaymentMethod.TRANSFER,
        items=[(variant.id, 1)],
        member=False,
    )
    db_session.commit()
    line_id = order.lines[0].id

    headers = board_session(client)
    response = client.post(f"/admin/verkoop/{order.id}/lijn/{line_id}/leveren", headers=headers)
    assert response.status_code == 422
    assert "leverancier" in response.text


def test_a_line_without_an_open_reservation_is_not_delivered(db_session, every_module_on):
    """A line whose reservation is gone is refused, never marked delivered, and the
    stock does not move — the stock and the state never disagree (B2)."""
    from app.domains.mdm.api import PaymentMethod
    from app.domains.sales.api import SalesError, deliver_line, place_order
    from app.domains.sales.models import SalesOrderLine
    from app.domains.stock.api import available, release

    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    order = place_order(
        db_session,
        person_id=None,
        guest_name="An",
        guest_email="an@example.com",
        guest_mobile="0470000000",
        method=PaymentMethod.TRANSFER,
        items=[(m.id, 1)],
        member=False,
    )
    db_session.commit()
    line_id = order.lines[0].id
    release(db_session, line_id)
    db_session.commit()

    with pytest.raises(SalesError):
        deliver_line(db_session, order.id, line_id, actor="beheerder@example.com")

    db_session.expire_all()
    line = db_session.query(SalesOrderLine).filter(SalesOrderLine.id == line_id).one()
    assert line.delivered_at is None
    assert available(db_session, m.id) == 5


def test_a_second_delivery_is_refused(db_session, every_module_on):
    """B1: a second delivery of one line is a refusal, not a silent no-op."""
    from app.domains.mdm.api import PaymentMethod
    from app.domains.sales.api import SalesError, deliver_line, place_order

    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    order = place_order(
        db_session,
        person_id=None,
        guest_name="An",
        guest_email="an@example.com",
        guest_mobile="0470000000",
        method=PaymentMethod.TRANSFER,
        items=[(m.id, 1)],
        member=False,
    )
    db_session.commit()
    deliver_line(db_session, order.id, order.lines[0].id, actor="beheerder@example.com")

    with pytest.raises(SalesError) as refused:
        deliver_line(db_session, order.id, order.lines[0].id, actor="beheerder@example.com")
    assert "al geleverd" in str(refused.value)


def test_cancelling_a_paid_order_leaves_the_full_refund_due(db_session, every_module_on):
    """B3: cancelling a paid order names a refund in the confirm text and leaves the
    full amount due, pending — the charge stays paid and a refund of the whole
    amount waits to be confirmed."""
    from app.domains.mdm.api import PaymentMethod
    from app.domains.payment.api import PayableType, open_refund_amount
    from app.domains.payment.models import PaymentRecord
    from app.domains.payment.service import confirm_manual_payment
    from app.domains.sales.api import cancel_order, submit_order

    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    _checkout, order_id = submit_order(
        db_session,
        person_id=None,
        member=False,
        contact_name="An",
        contact_email="an@example.com",
        phone="0470000000",
        method=PaymentMethod.TRANSFER,
        items=[(m.id, 1)],
    )
    record = (
        db_session.query(PaymentRecord)
        .filter(
            PaymentRecord.payable_type == PayableType.ORDER,
            PaymentRecord.payable_id == order_id,
        )
        .one()
    )
    confirm_manual_payment(db_session, record.id, amount_paid=Decimal("15.00"), actor="test")
    db_session.commit()

    cancel_order(db_session, order_id, actor="beheerder@example.com")

    assert open_refund_amount(db_session, PayableType.ORDER, order_id) == Decimal("15.00")


def test_the_verkoop_list_segments_and_counter_follow_the_filter(
    client, db_session, every_module_on
):
    """B1/B2 of the review: the fragment route's segments and its toolbar counter
    follow the filter — the right rows per segment, and "x–y van n" matches."""
    from app.domains.mdm.api import PaymentMethod
    from app.domains.payment.api import PayableType
    from app.domains.payment.models import PaymentRecord
    from app.domains.payment.service import confirm_manual_payment
    from app.domains.sales.api import submit_order
    from tests.conftest import board_session

    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)

    _checkout, unpaid_id = submit_order(
        db_session,
        person_id=None,
        member=False,
        contact_name="An",
        contact_email="an@example.com",
        phone="0470000000",
        method=PaymentMethod.TRANSFER,
        items=[(m.id, 1)],
    )
    _checkout, paid_id = submit_order(
        db_session,
        person_id=None,
        member=False,
        contact_name="Bo",
        contact_email="bo@example.com",
        phone="0470000001",
        method=PaymentMethod.TRANSFER,
        items=[(m.id, 1)],
    )
    record = (
        db_session.query(PaymentRecord)
        .filter(
            PaymentRecord.payable_type == PayableType.ORDER,
            PaymentRecord.payable_id == paid_id,
        )
        .one()
    )
    confirm_manual_payment(db_session, record.id, amount_paid=Decimal("15.00"), actor="test")
    db_session.commit()

    board_session(client)

    def _lijst(query: str) -> tuple[int, str]:
        response = client.get(f"/admin/verkoop/lijst{query}")
        assert response.status_code == 200
        return response.text.count("<tr data-row"), response.text

    alles, alles_html = _lijst("?segment=alles")
    assert alles == 2
    assert "1–2 van 2" in alles_html

    te_betalen, _ = _lijst("?segment=te-betalen")
    assert te_betalen == 1
    te_leveren, _ = _lijst("?segment=te-leveren")
    assert te_leveren == 1

    op_id, _ = _lijst(f"?q={unpaid_id}")
    assert op_id == 1
    geen, geen_html = _lijst("?q=zzz")
    assert geen == 0
    assert "Geen bestelling gevonden" in geen_html
    assert "0–0 van 0" in geen_html


def test_bestelling_toevoegen_hangs_on_the_typed_person_and_his_member_price(
    client, db_session, every_module_on
):
    """T22/R43/F18: Verkoop's order hangs on the person of the typed address and
    carries his member price — never the seller's."""
    from app.domains.membership.api import Membership
    from app.domains.product.api import add_variant, create_product, set_status
    from app.domains.sales.models import SalesOrder, SalesOrderLine
    from tests.conftest import board_session, create_test_family

    member, person = create_test_family(db_session, email="lid@example.com")
    today = date.today()
    db_session.add(
        Membership(
            member_id=member.id,
            year=today.year,
            is_active=True,
            valid_from=date(today.year, 1, 1),
            valid_to=date(today.year, 12, 31),
        )
    )
    product = create_product(db_session, "T-shirt")
    set_status(db_session, product.id, ProductStatus.ON_SALE)
    variant = add_variant(db_session, product.id, "M")
    add_prices(
        db_session,
        product_id=product.id,
        variant_id=variant.id,
        valid_from=date(2026, 1, 1),
        amount=Decimal("15.00"),
        member_amount=Decimal("10.00"),
    )
    receive(db_session, variant.id, quantity=5)
    db_session.commit()

    headers = board_session(client)
    response = client.post(
        "/admin/verkoop/nieuw",
        data={
            "action": "save",
            "email": "lid@example.com",
            "variant_id": str(variant.id),
            "quantity": "1",
            "payment_method": "transfer",
        },
        headers=headers,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].startswith("/admin/verkoop/")

    order = db_session.query(SalesOrder).one()
    assert order.person_id == person.id
    line = db_session.query(SalesOrderLine).one()
    assert line.unit_price == Decimal("10.00")


def test_bestelling_toevoegen_refuses_a_short_article(client, db_session, every_module_on):
    """T22: a short article is refused through the board's order, as on the public
    page — a 422, not a 500."""
    from tests.conftest import board_session, create_test_family

    create_test_family(db_session, email="lid@example.com")
    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=1)
    db_session.commit()

    headers = board_session(client)
    response = client.post(
        "/admin/verkoop/nieuw",
        data={
            "action": "save",
            "email": "lid@example.com",
            "variant_id": str(m.id),
            "quantity": "2",
            "payment_method": "transfer",
        },
        headers=headers,
    )
    assert response.status_code == 422
    assert "voorraad" in response.text


def _board_user(db, role: str, email: str) -> str:
    from app.domains.auth.api import User, UserRole
    from app.kernel.tenancy import TENANT_MILLEGEM_ID

    user = User(email=email, is_active=True)
    db.add(user)
    db.flush()
    db.add(UserRole(user_id=user.id, role_code=role, tenant_id=TENANT_MILLEGEM_ID))
    db.commit()
    return email


def _as(client, email: str) -> dict:
    from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value

    value = make_session_value(email)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def test_de_koppeling_noemt_nooit_een_naam(client, db_session, every_module_on):
    """A1 (CR-24 AC6): the link line says the address is known, never who it is."""
    from tests.conftest import create_test_family

    create_test_family(db_session, email="lid@example.com")
    db_session.commit()
    headers = _as(client, _board_user(db_session, "SALES", "verkoper@example.com"))

    answer = client.post(
        "/admin/verkoop/nieuw/koppeling", data={"email": "lid@example.com"}, headers=headers
    )
    assert answer.status_code == 200
    assert "bestaand lid" in answer.text
    assert "Persoon" not in answer.text, "the link line must not name the person"


def test_de_helpers_vragen_manage(client, db_session, every_module_on):
    """A1: a board user without `sales.manage` is refused the two helpers."""
    _as(client, _board_user(db_session, "MASTERDATA", "masterdata@example.com"))
    for path in ("/admin/verkoop/nieuw/koppeling", "/admin/verkoop/nieuw/maten"):
        assert client.post(path, data={"email": "lid@example.com"}).status_code == 403, path


def test_het_bestuur_biedt_alleen_overschrijving_aan(client, db_session, every_module_on):
    """A2: the board's form offers no online choice, and a posted online choice is
    refused."""
    from tests.conftest import create_test_family

    create_test_family(db_session, email="lid@example.com")
    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    db_session.commit()
    headers = _as(client, _board_user(db_session, "SALES", "verkoper@example.com"))

    assert "Online betalen" not in client.get("/admin/verkoop/nieuw", headers=headers).text

    response = client.post(
        "/admin/verkoop/nieuw",
        data={
            "action": "save",
            "email": "lid@example.com",
            "variant_id": str(m.id),
            "quantity": "1",
            "payment_method": "online",
        },
        headers=headers,
    )
    assert response.status_code == 422
    assert "overschrijving" in response.text


def test_een_lijn_kan_verwijderd_worden(client, db_session, every_module_on):
    """B2: removing one line re-renders the form without it."""
    from tests.conftest import create_test_family

    create_test_family(db_session, email="lid@example.com")
    shirt = _variant_with_price_and_stock(
        db_session, name="T-shirt", size="M", amount="15.00", stock=5
    )
    zak = _variant_with_price_and_stock(db_session, name="Zak", size="M", amount="8.00", stock=5)
    db_session.commit()
    headers = _as(client, _board_user(db_session, "SALES", "verkoper@example.com"))

    body = (
        "email=lid@example.com"
        f"&variant_id={shirt.id}&variant_id={zak.id}"
        "&quantity=1&quantity=1"
        f"&remove_variant_id={zak.id}"
    )
    removed = client.post(
        "/admin/verkoop/nieuw",
        content=body,
        headers={"Content-Type": "application/x-www-form-urlencoded", **headers},
    )
    assert removed.status_code == 200
    assert f'name="variant_id" value="{shirt.id}"' in removed.text
    assert f'name="variant_id" value="{zak.id}"' not in removed.text


def test_een_onbekend_of_meervoudig_adres_wordt_geweigerd(client, db_session, every_module_on):
    """B3/B4: an unknown address and an address on several persons are each a 422."""
    from tests.conftest import create_test_family

    create_test_family(db_session, email="dubbel@example.com")
    create_test_family(db_session, email="dubbel@example.com")
    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    db_session.commit()
    headers = _as(client, _board_user(db_session, "SALES", "verkoper@example.com"))

    def _save(email: str) -> dict:
        return client.post(
            "/admin/verkoop/nieuw",
            data={
                "action": "save",
                "email": email,
                "variant_id": str(m.id),
                "quantity": "1",
                "payment_method": "transfer",
            },
            headers=headers,
        )

    unknown = _save("niemand@example.com")
    assert unknown.status_code == 422
    assert "niemand gekend" in unknown.text

    multiple = _save("dubbel@example.com")
    assert multiple.status_code == 422
    assert "meerdere" in multiple.text


def test_het_adres_wordt_genormaliseerd_op_hoofdletters_en_spaties(
    client, db_session, every_module_on
):
    """B4: an address typed with another case and spaces resolves the same person."""
    from app.domains.sales.models import SalesOrder
    from tests.conftest import create_test_family

    _member, person = create_test_family(db_session, email="lid@example.com")
    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    db_session.commit()
    headers = _as(client, _board_user(db_session, "SALES", "verkoper@example.com"))

    response = client.post(
        "/admin/verkoop/nieuw",
        data={
            "action": "save",
            "email": "  LID@example.com  ",
            "variant_id": str(m.id),
            "quantity": "1",
            "payment_method": "transfer",
        },
        headers=headers,
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert db_session.query(SalesOrder).one().person_id == person.id


def test_een_bestelling_op_een_persoon_bewaart_geen_getypt_adres(
    client, db_session, every_module_on
):
    """B5: an order that hangs on a person stores no typed address."""
    from app.domains.sales.models import SalesOrder
    from tests.conftest import create_test_family

    _member, person = create_test_family(db_session, email="lid@example.com")
    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    db_session.commit()
    headers = _as(client, _board_user(db_session, "SALES", "verkoper@example.com"))

    response = client.post(
        "/admin/verkoop/nieuw",
        data={
            "action": "save",
            "email": "lid@example.com",
            "variant_id": str(m.id),
            "quantity": "1",
            "payment_method": "transfer",
        },
        headers=headers,
        follow_redirects=False,
    )
    assert response.status_code == 303
    order = db_session.query(SalesOrder).one()
    assert order.person_id == person.id
    assert not (order.guest_email or "").strip()


def test_een_onbestaande_betaalwijze_is_een_weigering(client, db_session, every_module_on):
    """B2 of the read: a forged payment method is a refusal on its field, not a 500."""
    from tests.conftest import create_test_family

    create_test_family(db_session, email="lid@example.com")
    m = _variant_with_price_and_stock(db_session, name="T-shirt", size="M", amount="15.00", stock=5)
    db_session.commit()
    headers = _as(client, _board_user(db_session, "SALES", "verkoper@example.com"))

    response = client.post(
        "/admin/verkoop/nieuw",
        data={
            "action": "save",
            "email": "lid@example.com",
            "variant_id": str(m.id),
            "quantity": "1",
            "payment_method": "bitcoin",
        },
        headers=headers,
    )
    assert response.status_code == 422
    assert "overschrijving" in response.text


def test_een_account_zonder_lidmaatschap_wordt_zo_genoemd(client, db_session, every_module_on):
    """B3 of the read: an address that signs in as an account (no household) reads
    "bekend account", never "bestaand lid"."""
    from app.domains.mdm.api import ContactDetail
    from tests.conftest import create_test_person

    person = create_test_person(db_session, first_name="An", last_name="Zonder")
    db_session.add(
        ContactDetail(
            person_id=person.id,
            contact_type_code="EMAIL",
            value="account@example.com",
            is_primary=True,
        )
    )
    db_session.commit()
    headers = _as(client, _board_user(db_session, "SALES", "verkoper@example.com"))

    answer = client.post(
        "/admin/verkoop/nieuw/koppeling", data={"email": "account@example.com"}, headers=headers
    )
    assert answer.status_code == 200
    assert "bekend account" in answer.text
    assert "bestaand lid" not in answer.text
