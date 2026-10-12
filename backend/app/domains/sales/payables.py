"""A webshop order as a payable: how `payment` learns what an order's payment is
for (CR-21 Q48). Registered for `PayableType.ORDER` in `app/main.py`.

Soft-deleted orders are read too, because a payment is a financial fact and keeps
showing the name it was made under (#190).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable

from sqlalchemy.orm import Session

from app.domains.sales.models import SalesOrder

if TYPE_CHECKING:
    from app.domains.payment.api import Describer, PayableDescription


def _q(db: Session, model):
    return db.query(model).execution_options(include_deleted=True)


def describe_orders(db: Session, ids: Iterable[int]) -> dict[int, "PayableDescription"]:
    """`{order_id: PayableDescription}` — the buyer's name, in as few queries as it
    takes."""
    from app.domains.mdm.api import Person
    from app.domains.payment.api import PayableDescription

    wanted = set(ids)
    if not wanted:
        return {}
    orders = _q(db, SalesOrder).filter(SalesOrder.id.in_(wanted)).all()
    person_ids = {order.person_id for order in orders if order.person_id}
    persons = (
        {p.id: p for p in _q(db, Person).filter(Person.id.in_(person_ids)).all()}
        if person_ids
        else {}
    )
    described = {}
    for order in orders:
        person = persons.get(order.person_id) if order.person_id else None
        contact = order.guest_name
        if not contact and person is not None:
            contact = f"{person.first_name} {person.last_name}".strip()
        described[order.id] = PayableDescription(
            contact_name=contact,
            description=f"Bestelling {order.id}",
            person_id=order.person_id,
            contact_email=order.guest_email,
        )
    return described


def orders_of_household(db: Session, household_id: int) -> list[int]:
    """The orders of a household's persons (the household's payments tab)."""
    from app.domains.mdm.api import MemberPerson

    person_ids = [
        row[0]
        for row in db.query(MemberPerson.person_id)
        .filter(MemberPerson.member_id == household_id)
        .all()
    ]
    if not person_ids:
        return []
    return [
        row[0] for row in db.query(SalesOrder.id).filter(SalesOrder.person_id.in_(person_ids)).all()
    ]


def order_describer() -> "Describer":
    """The describer `app/main.py` registers for `PayableType.ORDER`."""
    from app.domains.payment.api import Describer

    return Describer(
        describe=describe_orders,
        of_household=orders_of_household,
        export_kind="Bestelling",
        payable_page=lambda order_id: f"/admin/verkoop/{order_id}",
        payable_label="Bestelling",
    )
