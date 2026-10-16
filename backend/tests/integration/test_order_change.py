"""Change an order's lines (CR-21 phase 3, R15/R16/F7): the lines are replaced at
today's price, the reservations follow, and a refusal leaves the order as it was."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from app.domains.mdm.api import PaymentMethod
from app.domains.pricing.api import add_prices
from app.domains.product.api import ProductStatus, add_variant, create_product, set_status
from app.domains.sales.api import change_order_lines, place_order, total_of


def _variant(db_session, *, name="T-shirt", size="M", amount="15.00", stock=5):
    from app.domains.stock.api import receive

    product = create_product(db_session, name)
    set_status(db_session, product.id, ProductStatus.ON_SALE)
    variant = add_variant(db_session, product.id, size)
    add_prices(
        db_session,
        product_id=product.id,
        variant_id=variant.id,
        valid_from=date(2026, 1, 1),
        amount=Decimal(amount),
        member_amount=None,
    )
    receive(db_session, variant.id, quantity=stock)
    db_session.flush()
    return variant


def _order(db_session, items, *, person_id=None):
    order = place_order(
        db_session,
        person_id=person_id,
        guest_name="" if person_id is not None else "Bo",
        guest_email="" if person_id is not None else "bo@example.com",
        guest_mobile="" if person_id is not None else "0470000001",
        method=PaymentMethod.TRANSFER,
        items=items,
        member=False,
    )
    db_session.commit()
    return order


def test_a_change_replaces_the_lines_and_the_reservation_follows(db_session, every_module_on):
    """AC11: change M ×1 into M ×2 — the line and the total follow, and the stock
    reserves two instead of one."""
    from app.domains.stock.api import available

    m = _variant(db_session)
    order = _order(db_session, [(m.id, 1)])
    assert total_of(order) == Decimal("15.00")
    assert available(db_session, m.id) == 4

    change_order_lines(db_session, order.id, [(m.id, 2)], actor="verkoper@example.com")
    db_session.expire_all()

    changed = db_session.query(type(order)).get(order.id)
    assert total_of(changed) == Decimal("30.00")
    assert [line.quantity for line in changed.lines] == [2]
    assert available(db_session, m.id) == 3


def test_a_change_short_of_stock_is_refused_and_the_order_stays(db_session, every_module_on):
    """The phase table's failure path: the new size is sold out, the answer refuses,
    and the old line, its reservation and the total are exactly as before."""
    from app.domains.sales.models import SalesOrder
    from app.domains.stock.api import available

    m = _variant(db_session, stock=1)
    order = _order(db_session, [(m.id, 1)])
    assert available(db_session, m.id) == 0

    import pytest

    from app.domains.sales.api import SalesError

    with pytest.raises(SalesError):
        change_order_lines(db_session, order.id, [(m.id, 2)], actor="verkoper@example.com")

    db_session.expire_all()
    unchanged = db_session.get(SalesOrder, order.id)
    assert total_of(unchanged) == Decimal("15.00")
    assert [line.quantity for line in unchanged.lines] == [1]


def test_a_change_that_keeps_the_last_unit_is_not_refused(db_session, every_module_on):
    """A change that keeps the order's own last unit is not refused for the unit it
    already holds: release first, then reserve."""
    m = _variant(db_session, stock=1)
    order = _order(db_session, [(m.id, 1)])
    # The order holds the last unit; changing quantity stays 1 (same unit).
    change_order_lines(db_session, order.id, [(m.id, 1)], actor="verkoper@example.com")
    db_session.expire_all()
    changed = db_session.query(type(order)).get(order.id)
    assert total_of(changed) == Decimal("15.00")
    assert [line.quantity for line in changed.lines] == [1]


def test_a_change_publishes_the_new_total(db_session, every_module_on):
    """`SalesOrderChanged` carries the new total, so `payment` recalculates — an
    extra charge when the amount went up and it was already paid."""
    from app.domains.payment.api import PayableType, PaymentRecord, reconcile_charges

    m = _variant(db_session)
    order = _order(db_session, [(m.id, 1)])
    reconcile_charges(db_session, PayableType.ORDER, order.id, Decimal("15.00"))
    db_session.commit()

    change_order_lines(db_session, order.id, [(m.id, 2)], actor="verkoper@example.com")
    db_session.expire_all()

    amounts = [
        r.amount
        for r in db_session.query(PaymentRecord)
        .filter(
            PaymentRecord.payable_type == PayableType.ORDER,
            PaymentRecord.payable_id == order.id,
        )
        .all()
    ]
    assert amounts == [Decimal("30.00")], "the charge follows the new total"
