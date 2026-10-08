"""A registration as a payable: how `payment` learns what a registration's payment is
for (CR-21 Q48, #1748). Registered for `PayableType.REGISTRATION` in `app/main.py`.

Moved here from `payment` — `enriched_records`, the export's `_enrich` and
`family_payables` each knew a registration's tables — not rewritten: the same reads,
the same words, soft-deleted rows included, because a payment is a financial fact and
keeps showing the name it was made under (#190).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Iterable

from sqlalchemy import func, or_
from sqlalchemy.orm import Session, selectinload

from app.domains.activities.models import (
    Activity,
    ActivitySubRegistration,
    Registration,
    RegistrationItem,
)

if TYPE_CHECKING:
    from app.domains.payment.api import Describer, PayableDescription


def _q(db: Session, model: Any) -> Any:
    return db.query(model).execution_options(include_deleted=True)


def describe_registrations(db: Session, ids: Iterable[int]) -> dict[int, "PayableDescription"]:
    """`{registration_id: PayableDescription}`, in three queries whatever the count."""
    from app.domains.activities.totals import compute_registration_total
    from app.domains.payment.api import PayableDescription

    wanted = set(ids)
    if not wanted:
        return {}
    # The registrations with their items and products at once: the total walks them.
    registrations = (
        _q(db, Registration)
        .options(
            selectinload(Registration.items).selectinload(RegistrationItem.product),
            selectinload(Registration.person),
        )
        .filter(Registration.id.in_(wanted))
        .all()
    )
    activity_ids = {r.activity_id for r in registrations if r.activity_id}
    component_ids = {r.component_id for r in registrations if r.component_id}
    activities = (
        {a.id: a for a in _q(db, Activity).filter(Activity.id.in_(activity_ids)).all()}
        if activity_ids
        else {}
    )
    components = (
        {
            c.id: c
            for c in _q(db, ActivitySubRegistration)
            .filter(ActivitySubRegistration.id.in_(component_ids))
            .all()
        }
        if component_ids
        else {}
    )

    described = {}
    for reg in registrations:
        activity = activities.get(reg.activity_id)
        component = components.get(reg.component_id)
        items: list = []
        if activity is not None:
            _total, lines = compute_registration_total(reg)
            items = [
                {
                    "product_name": line["name"],
                    "quantity": line["quantity"],
                    "unit_price": float(line["unit_price"]),
                    "subtotal": float(line["subtotal"]),
                }
                for line in lines
            ]
        names = [reg.contact_name, activity.name if activity else None]
        described[reg.id] = PayableDescription(
            contact_name=reg.contact_name,
            description=activity.name if activity is not None else None,
            context_href=f"/admin/activiteiten/{reg.activity_id}" if reg.activity_id else None,
            filter_context=f"comp-{reg.component_id}" if reg.component_id is not None else None,
            export_label=" — ".join(n for n in names if n) or f"Inschrijving #{reg.id}",
            person_id=reg.person_id,
            contact_email=reg.contact_email,
            record_fields={
                "component_id": reg.component_id,
                "component_name": component.name if component else None,
                "items": items,
            },
        )
    return described


def registrations_of_household(db: Session, household_id: int) -> list[int]:
    """The registrations of a household's persons — by person, and by e-mail address
    for a guest registration (the same rule as the audit resolver)."""
    from app.domains.mdm.api import CONTACT, ContactDetail, MemberPerson

    person_ids = [
        row[0]
        for row in _q(db, MemberPerson.person_id)
        .filter(MemberPerson.member_id == household_id)
        .all()
    ]
    emails = [
        row[0].strip().lower()
        for row in _q(db, ContactDetail.value)
        .filter(
            ContactDetail.person_id.in_(person_ids or [0]),
            ContactDetail.contact_type_code == CONTACT.EMAIL,
        )
        .all()
        if row[0]
    ]
    conditions = []
    if person_ids:
        conditions.append(Registration.person_id.in_(person_ids))
    if emails:
        conditions.append(func.lower(Registration.contact_email).in_(emails))
    if not conditions:
        return []
    return [row[0] for row in _q(db, Registration.id).filter(or_(*conditions)).all()]


def registration_describer() -> "Describer":
    """The describer `app/main.py` registers for `PayableType.REGISTRATION`."""
    from app.domains.payment.api import Describer

    return Describer(
        describe=describe_registrations,
        of_household=registrations_of_household,
        export_kind="Activiteit",
        payable_page=lambda registration_id: f"/admin/inschrijvingen/{registration_id}",
        payable_label="Inschrijving",
        filter_prefix="comp-",
    )
