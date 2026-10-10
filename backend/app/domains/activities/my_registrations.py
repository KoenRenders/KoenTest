"""Mijn inschrijvingen: the registrations a signed-in person sees (CR-22 S5,
#1709; R8, R23, R27; F8).

A member sees his household's registrations, anyone else his own — by the
person a registration is linked to (`Registration.person_id`), never by an
e-mail address: a guest's registration has no person and is in nobody's list
(R23), and one the board made on the address of a person is linked to that
person and so stands here (Koen, 7 October 2026).

Each with its payment state from the payment facade — what the bookings say
together — and, while a transfer is still to make, the transfer itself (R27).
No list of payments: a registration and how it stands (R8).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from sqlalchemy.orm import Session, selectinload

from app.domains.activities.models import Registration, RegistrationItem


@dataclass(frozen=True)
class MyRegistration:
    """One registration as its card shows it."""

    id: int
    activity_name: str
    #: The activity's public page.
    activity_href: str
    #: The activity's first date, None for an activity without one.
    activity_date: Optional[date]
    #: The component, "" where the activity has one and its name says nothing.
    component_name: str
    #: What was ordered, one line per product: "2 × Volwassene".
    lines: tuple[str, ...]
    #: What the bookings ask together; None when there is nothing to pay.
    amount: Optional[Decimal]
    #: There is something to pay or paid: the card shows the amount and how it stands.
    has_payment: bool
    #: Money still has to move (the payment facade's "open").
    to_pay: bool
    #: Who of the household registered — only where a household is shown (Q37).
    registered_by: Optional[str]
    registered_on: Optional[date]
    #: The transfer still to make (`payment.api.TransferDue`), None otherwise.
    transfer: Optional[Any] = None


def person_ids_seen_by(person: Any) -> tuple[list[int], bool]:
    """Whose registrations this person sees, and whether that is a household:
    every person of his household, or himself alone."""
    links = [link for link in person.member_persons if link.deleted_at is None]
    if not links:
        return [person.id], False
    household = links[0].member
    ids = [link.person_id for link in household.member_persons if link.deleted_at is None]
    return sorted(set(ids) | {person.id}), True


def _transfer(db: Session, state: dict) -> Optional[Any]:
    """The transfer this registration still asks for: its open booking, when
    that is a charge paid by bank transfer."""
    from app.domains.payment.api import PaymentRecord, transfer_due
    from app.i18n import _

    if not state.get("open_booking_ids") or state.get("open_booking_is_refund"):
        return None
    record = db.get(PaymentRecord, state["booking_id"])
    return transfer_due(db, record, _("Inschrijving geregistreerd — betaal via overschrijving:"))


def my_registrations(
    db: Session, person: Any, *, limit: Optional[int] = None
) -> list[MyRegistration]:
    """The registrations `person` sees, newest first; `limit` for the latest ones."""
    from app.domains.payment.api import registration_payment_states

    ids, household = person_ids_seen_by(person)
    query = (
        db.query(Registration)
        .filter(Registration.person_id.in_(ids))
        .options(
            selectinload(Registration.items).selectinload(RegistrationItem.product),
            selectinload(Registration.activity),
            selectinload(Registration.person),
        )
        .order_by(Registration.registered_at.desc(), Registration.id.desc())
    )
    if limit is not None:
        query = query.limit(limit)
    registrations = query.all()
    states = registration_payment_states(db, [r.id for r in registrations])
    rows = []
    for reg in registrations:
        activity = reg.activity
        dates = sorted(d.start_date for d in activity.dates if d.start_date is not None)
        state = states.get(reg.id)
        multi = len(activity.sub_registrations) > 1
        rows.append(
            MyRegistration(
                id=reg.id,
                activity_name=activity.name,
                activity_href=f"/activiteiten/{activity.slug or activity.id}",
                activity_date=dates[0] if dates else None,
                component_name=reg.component.name if multi and reg.component is not None else "",
                lines=tuple(
                    f"{item.quantity} × {item.product.name}"
                    for item in reg.items
                    if item.product is not None
                ),
                amount=state["due"] if state else None,
                has_payment=state is not None,
                to_pay=bool(state and state["open_booking_ids"]),
                registered_by=(reg.person.first_name or "").strip() or None
                if household and reg.person is not None
                else None,
                registered_on=reg.registered_at.date() if reg.registered_at else None,
                transfer=_transfer(db, state) if state else None,
            )
        )
    return rows
