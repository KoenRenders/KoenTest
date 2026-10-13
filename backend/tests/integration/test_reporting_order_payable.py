"""The order flows into the payments fact (CR-21, phase 2): `f_payments` joins a
third payable, and the registration and membership rows stay as they were.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlalchemy import text

from app.domains.mdm.api import Member, MemberPerson, Person
from app.domains.payment.api import PayableType, PaymentRecord
from app.domains.sales.api import SalesOrder, SalesOrderLine

pytestmark = pytest.mark.ui_agnostisch


def _order(db, *, person_id=None, guest_name=None):
    order = SalesOrder(person_id=person_id, guest_name=guest_name)
    db.add(order)
    db.flush()
    db.add(SalesOrderLine(order_id=order.id, variant_id=1, quantity=1, unit_price=Decimal("15.00")))
    db.flush()
    return order


def _charge(db, order):
    db.add(
        PaymentRecord(
            payable_type=PayableType.ORDER,
            payable_id=order.id,
            type="charge",
            amount=Decimal("15.00"),
            method="transfer",
            status="pending",
        )
    )
    db.flush()


def test_a_guest_order_flows_into_the_payments_fact(db_session):
    order = _order(db_session, guest_name="An Janssens")
    _charge(db_session, order)

    row = db_session.execute(
        text(
            "SELECT payable_type_label, payable_label, member_id FROM reporting.f_payments "
            "WHERE payable_type = 'order' AND payable_id = :id"
        ),
        {"id": order.id},
    ).one()

    assert row.payable_type_label == "Bestelling"
    assert row.payable_label == f"An Janssens — Bestelling {order.id}"
    assert row.member_id is None, "a guest has no household"


def test_a_members_order_carries_its_household(db_session):
    first = Member()
    db_session.add(first)
    db_session.flush()
    second = Member()
    db_session.add(second)
    db_session.flush()
    person = Person(
        first_name="Piet", last_name="Peeters", date_of_birth="1980-05-01", gender_code="M"
    )
    db_session.add(person)
    db_session.flush()
    # two households: the head's comes first, so the fact holds one row, the head's
    db_session.add(MemberPerson(member_id=first.id, person_id=person.id, relation_type="HOOFDLID"))
    db_session.add(MemberPerson(member_id=second.id, person_id=person.id, relation_type="HOOFDLID"))
    db_session.flush()

    order = _order(db_session, person_id=person.id)
    _charge(db_session, order)

    row = db_session.execute(
        text(
            "SELECT member_id, payable_label FROM reporting.f_payments "
            "WHERE payable_type = 'order' AND payable_id = :id"
        ),
        {"id": order.id},
    ).one()

    assert row.member_id == first.id
    assert "Piet Peeters" in row.payable_label
