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
    assert available(db_session, m.id) == 0, "the reservation is as it was"


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


def test_a_line_the_change_leaves_alone_keeps_its_price(db_session, every_module_on):
    """A2/Koen "2a": a line the change leaves alone keeps its price; a new line takes
    today's price."""
    m = _variant(db_session, size="M", amount="15.00")
    large = _variant(db_session, size="L", amount="20.00")
    order = _order(db_session, [(m.id, 1)])
    for line in order.lines:
        line.unit_price = Decimal("10.00")  # an older fixed price
    db_session.commit()

    change_order_lines(
        db_session, order.id, [(m.id, 1), (large.id, 1)], actor="verkoper@example.com"
    )
    db_session.expire_all()
    changed = db_session.query(type(order)).get(order.id)
    prices = {line.variant_id: line.unit_price for line in changed.lines}
    assert prices[m.id] == Decimal("10.00"), "the unchanged line keeps its old price"
    assert prices[large.id] == Decimal("20.00"), "the new line takes today's price"


def test_a_delivered_line_refuses_the_change_but_others_can_still_change(
    db_session, every_module_on
):
    """B3: a change that touches a delivered line is refused, naming it; the other
    lines can still change."""
    import pytest

    from app.domains.sales.api import SalesError

    m = _variant(db_session, size="M", amount="15.00", stock=5)
    large = _variant(db_session, size="L", amount="20.00", stock=5)
    order = _order(db_session, [(m.id, 1), (large.id, 1)])
    delivered = order.lines[0]
    delivered.delivered_at = date.today()
    db_session.commit()

    with pytest.raises(SalesError, match="Maat M is al geleverd"):
        change_order_lines(db_session, order.id, [(large.id, 2)], actor="verkoper@example.com")

    # The L line alone can still change.
    change_order_lines(
        db_session, order.id, [(m.id, 1), (large.id, 2)], actor="verkoper@example.com"
    )
    db_session.expire_all()
    changed = db_session.query(type(order)).get(order.id)
    assert total_of(changed) == Decimal("55.00")


def test_a_change_splits_a_line(db_session, every_module_on):
    """A5/F7: the change may split an undelivered line — 3 × M into 1 + 2 — and the
    sum and the total stay."""
    m = _variant(db_session, size="M", amount="15.00", stock=5)
    order = _order(db_session, [(m.id, 3)])
    assert total_of(order) == Decimal("45.00")

    change_order_lines(db_session, order.id, [(m.id, 1), (m.id, 2)], actor="verkoper@example.com")
    db_session.expire_all()
    changed = db_session.query(type(order)).get(order.id)
    assert sorted(line.quantity for line in changed.lines) == [1, 2]
    assert total_of(changed) == Decimal("45.00")


def _submitted_order(db_session, items, *, person_id=None, method=PaymentMethod.TRANSFER):
    from app.domains.sales.api import submit_order
    from app.kernel.form_guard import TRUSTED
    from tests.conftest import form_guard_fields

    _checkout, order_id, _key = submit_order(
        db_session,
        proof=TRUSTED,
        values=form_guard_fields(),
        person_id=person_id,
        member=False,
        contact_name="" if person_id is not None else "Bo",
        contact_email="" if person_id is not None else "bo@example.com",
        phone="" if person_id is not None else "0470000001",
        method=method,
        items=items,
    )
    return order_id


def _records(db_session, order_id):
    from app.domains.payment.api import PayableType, get_records_for

    return get_records_for(db_session, PayableType.ORDER, order_id)


def _pay(db_session, order_id):
    from app.domains.payment.api import confirm_manual_payment

    (record,) = _records(db_session, order_id)
    confirm_manual_payment(
        db_session, record.id, amount_paid=record.amount, actor="penning@example.com"
    )


def test_a_change_up_after_payment_makes_an_extra_charge(db_session, every_module_on):
    """T8: paid, then up → an extra charge of the difference."""
    m = _variant(db_session, amount="15.00", stock=5)
    order_id = _submitted_order(db_session, [(m.id, 1)])
    _pay(db_session, order_id)

    change_order_lines(db_session, order_id, [(m.id, 2)], actor="verkoper@example.com")
    db_session.expire_all()

    records = _records(db_session, order_id)
    paid = [r for r in records if r.amount_paid is not None]
    open_ = [r for r in records if r.amount_paid is None]
    assert sum((r.amount_paid or 0) for r in paid) == Decimal("15.00")
    assert [r.amount for r in open_] == [Decimal("15.00")], "an extra charge of the difference"


def test_a_change_down_after_payment_makes_a_refund_due(db_session, every_module_on):
    """T8: paid, then down → a refund due."""
    m = _variant(db_session, amount="15.00", stock=5)
    order_id = _submitted_order(db_session, [(m.id, 2)])
    _pay(db_session, order_id)

    change_order_lines(db_session, order_id, [(m.id, 1)], actor="verkoper@example.com")
    db_session.expire_all()

    records = _records(db_session, order_id)
    from app.domains.payment.models import PaymentType

    refunds = [r for r in records if r.type == PaymentType.REFUND]
    assert [r.amount for r in refunds] == [Decimal("-15.00")], "a refund of the difference"


def test_a_change_before_payment_makes_a_new_amount(db_session, every_module_on):
    """T8: unpaid → a new amount, one open charge."""
    m = _variant(db_session, amount="15.00", stock=5)
    order_id = _submitted_order(db_session, [(m.id, 1)])

    change_order_lines(db_session, order_id, [(m.id, 2)], actor="verkoper@example.com")
    db_session.expire_all()

    records = _records(db_session, order_id)
    assert [r.amount for r in records] == [Decimal("30.00")]
    assert all(r.amount_paid is None for r in records)


def test_a_partly_paid_order_keeps_the_paid_part_closed(db_session, every_module_on):
    """T8: a partly paid order — the paid part closes, the rest is one open charge."""
    from app.domains.payment.api import confirm_manual_payment

    m = _variant(db_session, amount="15.00", stock=5)
    order_id = _submitted_order(db_session, [(m.id, 2)])
    (record,) = _records(db_session, order_id)
    confirm_manual_payment(
        db_session, record.id, amount_paid=Decimal("15.00"), actor="penning@example.com"
    )

    change_order_lines(db_session, order_id, [(m.id, 3)], actor="verkoper@example.com")
    db_session.expire_all()

    records = _records(db_session, order_id)
    paid = [r for r in records if r.amount_paid is not None]
    open_ = [r for r in records if r.amount_paid is None]
    assert [r.amount for r in paid] == [Decimal("15.00")], "the paid part stays closed"
    assert [r.amount for r in open_] == [Decimal("30.00")], "the rest is one open charge"


def test_a_change_drops_the_online_checkout(db_session, every_module_on, monkeypatch):
    """A1: an unpaid online order, changed, loses its online booking to a transfer —
    the order page then says the betaallink is vervallen (online_checkout_stale)."""
    from app.domains.payment.providers import mollie
    from app.domains.payment.providers.base import PaymentResult
    from app.domains.sales.api import order_view
    from app.domains.sales.models import SalesOrder

    monkeypatch.setattr(
        mollie.MollieProvider,
        "create_payment",
        lambda self, amount, description, redirect_url, webhook_url, metadata: PaymentResult(
            provider_payment_id="tr_a1_stale",
            checkout_url="https://mollie.test/checkout/tr_a1_stale",
            status="pending",
        ),
    )

    m = _variant(db_session, amount="15.00", stock=5)
    order_id = _submitted_order(db_session, [(m.id, 1)], method=PaymentMethod.ONLINE)
    order = db_session.get(SalesOrder, order_id)
    assert order_view(db_session, order)["online_checkout_stale"] is False

    change_order_lines(db_session, order_id, [(m.id, 2)], actor="verkoper@example.com")
    db_session.expire_all()
    order = db_session.get(SalesOrder, order_id)
    assert order_view(db_session, order)["online_checkout_stale"] is True


def test_the_form_and_the_save_give_one_total(db_session, every_module_on):
    """A6: after a price change, the change form shows a kept line at the price the
    save will write — the form's total and the written total are equal."""
    from app.domains.sales.api import basket_lines, change_plan

    m = _variant(db_session, size="M", amount="15.00")
    large = _variant(db_session, size="L", amount="20.00")
    order = _order(db_session, [(m.id, 1)])
    for line in order.lines:
        line.unit_price = Decimal("10.00")  # an older fixed price
    db_session.commit()

    target = [(m.id, 1), (large.id, 1)]
    kept_prices, _create, _remove = change_plan(db_session, order, target)
    form_lines = basket_lines(db_session, member=False, items=target, kept_prices=kept_prices)
    form_total = sum((line["price"] * line["quantity"] for line in form_lines), Decimal("0"))

    change_order_lines(db_session, order.id, target, actor="verkoper@example.com")
    db_session.expire_all()
    changed = db_session.query(type(order)).get(order.id)

    assert kept_prices[(m.id, 1)] == Decimal("10.00"), "the kept line keeps its old price"
    assert form_total == total_of(changed) == Decimal("30.00"), "the form and the save agree"


def test_a_delivered_twin_is_kept_and_the_undelivered_one_removed(db_session, every_module_on):
    """B3: two identical lines, one delivered — a change to one of them keeps the
    delivered line and removes the undelivered one, never leaving a dangling
    delivered line."""
    m = _variant(db_session, size="M", amount="15.00", stock=5)
    order = _order(db_session, [(m.id, 1), (m.id, 1)])
    order.lines[0].delivered_at = date.today()  # the delivered twin
    db_session.commit()

    change_order_lines(db_session, order.id, [(m.id, 1)], actor="verkoper@example.com")
    db_session.expire_all()
    changed = db_session.query(type(order)).get(order.id)

    assert [line.quantity for line in changed.lines] == [1]
    assert changed.lines[0].delivered_at is not None, "the delivered line is the one kept"


def test_the_x_removes_one_line_after_a_split(db_session, every_module_on):
    """B5: the × removes one line only, so after a split it removes one half and the
    other stays (the remove action drops the posted position, not the variant)."""
    m = _variant(db_session, size="M", amount="15.00", stock=5)
    order = _order(db_session, [(m.id, 3)])
    change_order_lines(db_session, order.id, [(m.id, 1), (m.id, 2)], actor="verkoper@example.com")
    db_session.expire_all()
    split = db_session.query(type(order)).get(order.id)
    assert sorted(line.quantity for line in split.lines) == [1, 2]

    # Remove the first half (position 0) and save: the other half stays.
    change_order_lines(db_session, order.id, [(m.id, 2)], actor="verkoper@example.com")
    db_session.expire_all()
    changed = db_session.query(type(order)).get(order.id)
    assert [line.quantity for line in changed.lines] == [2]
    assert total_of(changed) == Decimal("30.00")


def test_the_x_posts_one_line_only(client, db_session, every_module_on):
    """B5: the × posts the line's position, so the change form removes one half of a
    split and keeps the other."""
    from tests.conftest import board_session

    headers = board_session(client)
    m = _variant(db_session, size="M", amount="15.00", stock=5)
    order = _order(db_session, [(m.id, 3)])
    change_order_lines(db_session, order.id, [(m.id, 1), (m.id, 2)], actor="verkoper@example.com")

    answer = client.post(
        f"/admin/verkoop/{order.id}/wijzigen",
        data={"variant_id": [m.id, m.id], "quantity": ["1", "2"], "remove_index": "0"},
        headers=headers,
    )
    assert answer.status_code == 200, answer.text[:300]
    assert "maat M · 2 ×" in answer.text, "the other half stays on the form"
    assert "maat M · 1 ×" not in answer.text, "the removed half is gone"
