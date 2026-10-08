"""Snapshot-helpers die een momentopname van een bron-rij in de bijbehorende
history-tabel wegschrijven.

Elke helper doet enkel ``db.add(...)`` en GEEN commit: de history-rij commit mee
in dezelfde transactie als de wijziging zelf (atomair — of allebei, of geen van
beide). Roep de helper dus aan vóór de ``db.commit()`` van de caller, en bij een
verwijdering vóór de ``db.delete(...)`` zodat de bron nog uitleesbaar is.
"""

from typing import Optional

from sqlalchemy.orm import Session

from app.domains.mdm.api import (
    AddressHistory,
    ContactDetailHistory,
    MemberHistory,
    MemberPersonHistory,
    PersonHistory,
)
from app.domains.membership.api import MembershipHistory
from app.kernel.codes import code_of

# #713: wat er in `actor` staat wanneer er níemand aangemeld was.
#
# Leeg betekende twee dingen tegelijk — "er was niemand aangemeld" én "we zijn
# vergeten wie dit deed" — en het scherm toont allebei als een lege cel. Daardoor kon
# niemand zo'n cel lezen, en kon een volgende vergetelheid er ongemerkt bij komen; zo
# zijn de vier ontstaan die dit issue rechtzet.
#
# Vanaf nu schrijven de publieke wegen dit, en betekent leeg **fout**. Geen `@`, dus
# niet te verwarren met een e-mailadres. Bestaande rijen blijven leeg: die kunnen we
# niet met terugwerkende kracht duiden en horen we ook niet zo te behandelen.
PUBLIEKE_ACTOR = "publiek"


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


def snapshot_membership(
    db: Session,
    membership,
    *,
    operation: str,
    action: str,
    source: str,
    actor: Optional[str] = None,
) -> None:
    db.add(
        MembershipHistory(
            membership_id=membership.id,
            member_id=membership.member_id,
            year=membership.year,
            is_active=membership.is_active,
            valid_from=membership.valid_from,
            valid_to=membership.valid_to,
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
