"""The history of a person and a household: the snapshots that write a row of this domain's
history tables (`docs/architecture.md` §5.8 — a history table per component,
written by its owner).

Moved here unchanged from `audit/service.py` (CR-13 phase 4c, #1251). A helper
only adds the row and never commits: the history row is committed in the same
transaction as the change it records. Call it before the caller's commit, and
before a delete, while the source can still be read.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.domains.mdm.models import (
    AddressHistory,
    ContactDetailHistory,
    MemberHistory,
    MemberPersonHistory,
    PersonHistory,
)
from app.kernel.codes import code_of


def snapshot_person(
    db: Session, person, *, operation: str, action: str, source: str, actor: Optional[str] = None
) -> None:
    db.add(
        PersonHistory(
            person_id=person.id,
            last_name=person.last_name,
            first_name=person.first_name,
            date_of_birth=person.date_of_birth,
            gender_code=code_of(person.gender_code),
            operation=operation,
            action=action,
            source=source,
            actor=actor,
        )
    )


def snapshot_member(
    db: Session, member, *, operation: str, action: str, source: str, actor: Optional[str] = None
) -> None:
    db.add(
        MemberHistory(
            member_id=member.id,
            board_member_id=member.board_member_id,
            operation=operation,
            action=action,
            source=source,
            actor=actor,
        )
    )


def snapshot_member_person(
    db: Session, mp, *, operation: str, action: str, source: str, actor: Optional[str] = None
) -> None:
    db.add(
        MemberPersonHistory(
            member_person_id=mp.id,
            member_id=mp.member_id,
            person_id=mp.person_id,
            relation_type=code_of(mp.relation_type),
            operation=operation,
            action=action,
            source=source,
            actor=actor,
        )
    )


def snapshot_address(
    db: Session, address, *, operation: str, action: str, source: str, actor: Optional[str] = None
) -> None:
    db.add(
        AddressHistory(
            address_id=address.id,
            person_id=address.person_id,
            street=address.street,
            house_number=address.house_number,
            bus_number=address.bus_number,
            postal_code_id=address.postal_code_id,
            operation=operation,
            action=action,
            source=source,
            actor=actor,
        )
    )


def snapshot_contact_detail(
    db: Session, contact, *, operation: str, action: str, source: str, actor: Optional[str] = None
) -> None:
    db.add(
        ContactDetailHistory(
            contact_detail_id=contact.id,
            person_id=contact.person_id,
            contact_type_code=code_of(contact.contact_type_code),
            value=contact.value,
            is_primary=contact.is_primary,
            operation=operation,
            action=action,
            source=source,
            actor=actor,
        )
    )
