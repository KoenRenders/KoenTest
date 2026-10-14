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
