"""The history of a person and a household: the snapshots that write a row of this domain's
history tables (`docs/architecture.md` §5.8 — a history table per component,
written by its owner).

Moved here unchanged from `audit/service.py` (CR-13 phase 4c, #1251). A helper
only adds the row and never commits: the history row is committed in the same
transaction as the change it records. Call it before the caller's commit, and
before a delete, while the source can still be read.

#1885: what is logged is declared here, beside the history models, and the
row is written by the one snapshot (`kernel.logged.snapshot`) — every column of
the object but the technical moments, no copy of them per model any more.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.domains.mdm.models import (
    Address,
    AddressHistory,
    ContactDetail,
    ContactDetailHistory,
    ExternalNumber,
    ExternalNumberHistory,
    Member,
    MemberHistory,
    MemberPerson,
    MemberPersonHistory,
    Person,
    PersonHistory,
)
from app.kernel.logged import declare, snapshot

declare(
    Person,
    PersonHistory,
    key="person_id",
    not_logged={"party_id": "the person's party is made with it and never changes (CR-26 F1)"},
)
declare(Member, MemberHistory, key="member_id")
declare(MemberPerson, MemberPersonHistory, key="member_person_id")
declare(Address, AddressHistory, key="address_id")
declare(ContactDetail, ContactDetailHistory, key="contact_detail_id")
declare(
    ExternalNumber,
    ExternalNumberHistory,
    key="external_number_id",
    renamed={"source": "number_source"},
)


def snapshot_person(
    db: Session, person, *, operation: str, action: str, source: str, actor: Optional[str] = None
) -> None:
    snapshot(
        db, person, operation=operation, action=action, source=source, actor=actor, model=Person
    )


def snapshot_member(
    db: Session, member, *, operation: str, action: str, source: str, actor: Optional[str] = None
) -> None:
    snapshot(
        db, member, operation=operation, action=action, source=source, actor=actor, model=Member
    )


def snapshot_member_person(
    db: Session, mp, *, operation: str, action: str, source: str, actor: Optional[str] = None
) -> None:
    snapshot(
        db, mp, operation=operation, action=action, source=source, actor=actor, model=MemberPerson
    )


def snapshot_address(
    db: Session, address, *, operation: str, action: str, source: str, actor: Optional[str] = None
) -> None:
    snapshot(
        db, address, operation=operation, action=action, source=source, actor=actor, model=Address
    )


def snapshot_contact_detail(
    db: Session, contact, *, operation: str, action: str, source: str, actor: Optional[str] = None
) -> None:
    snapshot(
        db,
        contact,
        operation=operation,
        action=action,
        source=source,
        actor=actor,
        model=ContactDetail,
    )


def snapshot_external_number(
    db: Session, number, *, operation: str, action: str, source: str, actor: Optional[str] = None
) -> None:
    """#1885: the member number from another system is logged too (Koen, 15
    October 2026)."""
    snapshot(
        db,
        number,
        operation=operation,
        action=action,
        source=source,
        actor=actor,
        model=ExternalNumber,
    )
