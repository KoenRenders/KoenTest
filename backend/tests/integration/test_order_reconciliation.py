"""The order's money (CR-21, D4): the charge follows a changed order, once.

The subscriber `reconcile_order_on_change` brings an order's charges to the total
`sales` computes from the lines and publishes in `SalesOrderChanged`. The same
event twice leaves one charge. A cancelled order keeps its payment on the
household's tab.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.domains.mdm.api import Member, MemberPerson, Person
from app.domains.payment.api import PaymentRecord, reconcile_charges
from app.domains.sales.api import SalesOrder, SalesOrderLine, order_describer
from app.kernel.contracts.sales import SalesOrderChanged
from app.kernel.events import publish
from app.soft_delete import soft_delete

pytestmark = pytest.mark.ui_agnostisch


def _order_with_line(db, *, quantity=2, price="18.00", person_id=None):
    order = SalesOrder(person_id=person_id)
    db.add(order)
    db.flush()
    line = SalesOrderLine(
        order_id=order.id, variant_id=1, quantity=quantity, unit_price=Decimal(price)
    )
    db.add(line)
    db.flush()
    return order


def _charges(db, order_id):
    return (
        db.query(PaymentRecord)
        .filter(
            PaymentRecord.payable_type == "order",
            PaymentRecord.payable_id == order_id,
        )
        .all()
    )


def test_the_order_change_reconciles_to_the_orders_own_total_and_once(db_session):
    """The total comes from the order's lines, published in the event; the charge
    follows it, and the same event twice leaves one charge."""
    order = _order_with_line(db_session, quantity=2, price="18.00")
    # 2 × 18 = 36, computed from the lines — the publisher's own total
    reconcile_charges(db_session, "order", order.id, Decimal("36.00"))

    publish(SalesOrderChanged(order_id=order.id, total_due="18.00"), db_session)
    assert [r.amount for r in _charges(db_session, order.id)] == [Decimal("18.00")]

    publish(SalesOrderChanged(order_id=order.id, total_due="18.00"), db_session)
    assert [r.amount for r in _charges(db_session, order.id)] == [Decimal("18.00")], (
        "one charge, once"
    )


def test_the_describer_names_the_order(db_session):
    order = _order_with_line(db_session, quantity=1, price="15.00")
    order.guest_name = "An Janssens"
    db_session.flush()

    described = order_describer().describe(db_session, [order.id])
    assert described[order.id].description == f"Bestelling {order.id}"
    assert described[order.id].contact_name == "An Janssens"


def test_a_cancelled_order_stays_on_the_households_tab(db_session):
    """A4: `orders_of_household` reads a soft-deleted order too — a cancelled
    order's payment and refund stay visible (#190)."""
    household = Member()
    db_session.add(household)
    db_session.flush()
    person = Person(
        first_name="An", last_name="Janssens", date_of_birth="1980-05-01", gender_code="F"
    )
    db_session.add(person)
    db_session.flush()
    db_session.add(
        MemberPerson(member_id=household.id, person_id=person.id, relation_type="HOOFDLID")
    )
    db_session.flush()

    order = _order_with_line(db_session, quantity=1, price="15.00", person_id=person.id)
    soft_delete(order)
    db_session.flush()

    assert order_describer().of_household(db_session, household.id) == [order.id]
