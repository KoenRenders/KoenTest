"""A household's persons, changed by a member of that household (CR-13 phase 3, #1250).

The household and its persons are master data (Koen, 27 September 2026: *"gezin en
personen is mdm"*); the membership — the yearly record, its payment, the renewal
window — is `membership`'s. Until this phase the family portal's mutations (change a
person, add one, remove one) were implemented in `membership/household_router.py`
and reached through `membership.api` functions that called the JSON router: a
second domain writing `mdm`'s rows. They live here now, behind `mdm.api`; the
portal's two doors — the JSON route and the screen, both in `mdm` too — call them
and keep only what a door does: who is logged in and the status code.

Each mutation commits, as the other portal mutations of `mdm` (the e-mail
addresses) already did: a screen may not touch the session (#635 rule 2), so the
transaction ends where the rule does.

Same behaviour as before the move (R13), including the order of the checks. The
refusals are `MasterDataError`s, one kind per answer the door gives, so no door has
to read a message to pick a status code.

Every write logs an audit row with `source="member_self"`; the actor is the
e-mail address of the member who acted, which the door knows and passes in.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.domains.mdm.models import (
    ContactDetail,
    MasterDataError,
    Member,
    MemberPerson,
    Person,
    PostalCode,
    RelationType,
)
from app.soft_delete import soft_delete

SOURCE = "member_self"


class HouseholdNotFound(MasterDataError):
    """The logged-in person belongs to no household."""


class PersonNotFound(MasterDataError):
    """No person with that id."""


class OutsideHousehold(MasterDataError):
    """The person exists but belongs to another household."""


class CannotRemoveSelf(MasterDataError):
    """A member cannot remove themselves from their household."""


class HouseholdRefused(MasterDataError):
    """What was sent cannot be stored: a missing name, an unknown postal code. A
    missing birth date or gender is `PersonDetailsMissing`, the household link's own
    rule (#681), asked here before anything changes."""


def actor_of(person: Person) -> Optional[str]:
    """The acting member's e-mail address, for the audit rows — the first one, as the
    portal has always recorded it."""
    from app.domains.mdm.codes import CONTACT

    return next(
        (c.value for c in person.contact_details if c.contact_type_code == CONTACT.EMAIL), None
    )


def household_of(db: Session, person: Person) -> Member:
    """The household the logged-in person belongs to."""
    from app.i18n import _

    link = next((m for m in person.member_persons), None)
    household = (
        db.query(Member).filter(Member.id == link.member_id).first() if link is not None else None
    )
    if household is None:
        raise HouseholdNotFound(_("Geen gezin gevonden."))
    return household


def household_person(db: Session, household: Member, person_id: int) -> Person:
    """A person of this household, for a member of it to change.

    The household boundary of every portal mutation: without it, a member who
    knows another person's id could change that person.
    """
    from app.i18n import _

    target = db.query(Person).filter(Person.id == person_id).first()
    if target is None:
        raise PersonNotFound(_("Persoon niet gevonden."))
    if not any(link.member_id == household.id for link in target.member_persons):
        raise OutsideHousehold(_("Geen toegang tot dit gezin."))
    return target


def update_household_person(
    db: Session, household: Member, person_id: int, data: dict, *, actor: Optional[str]
) -> Person:
    """Change a person of the household: name, birth date, gender, address, contacts.

    Only these fields; the relation type, the household's board member and the
    external number are never touched from here. The committing door of the JSON
    API; the save of the whole household (`household_save`, #1590) calls the same
    cores inside its one transaction.
    """
    target = household_person(db, household, person_id)

    new: dict[str, Any] = {}
    for field in ("first_name", "last_name", "date_of_birth", "gender_code"):
        if field not in data:
            continue
        value = data[field] or None
        if field == "date_of_birth" and value is not None and not isinstance(value, date):
            value = date.fromisoformat(value)
        new[field] = value
    apply_person_fields(db, target, new, actor=actor)

    address_data = data.get("address")
    if "address" in data and address_data and target.address:
        apply_address(db, target, address_data, actor=actor)

    for type_code, key in (("EMAIL", "email"), ("PHONE", "phone"), ("MOBILE", "mobile")):
        if key in data:
            _upsert_contact(db, target, type_code, data[key], actor=actor)
    db.commit()
    db.refresh(target)
    return target


def apply_person_fields(
    db: Session, target: Person, new: dict[str, Any], *, actor: Optional[str]
) -> bool:
    """Write these person fields with their history, without committing (#1590:
    shared by `update_household_person` and the save of the whole household).
    Returns whether anything changed."""
    from app.domains.audit.api import snapshot_person

    # #681: judge the outcome — the portal does not always send every field — and
    # judge it before applying anything: a rollback after the change would also
    # throw away everything else in the same session.
    MemberPerson.require_details(
        new.get("date_of_birth", target.date_of_birth),
        new.get("gender_code", target.gender_code),
    )

    # Snapshot only what really changes (#188): a form sends every field, but an
    # unchanged field makes no history row.
    changed = False
    for field, value in new.items():
        if getattr(target, field) != value:
            setattr(target, field, value)
            changed = True
    if changed:
        snapshot_person(
            db, target, operation="update", action="person_updated", source=SOURCE, actor=actor
        )
    return changed


def apply_address(db: Session, target: Person, address_data: dict, *, actor: Optional[str]) -> None:
    """Change the existing address of this person with its history, without
    committing. Refuses a postal code that is not in the table."""
    from app.domains.audit.api import snapshot_address
    from app.i18n import _

    address = target.address
    address_changed = False
    for field in ("street", "house_number"):
        if field in address_data and address_data[field] is not None:
            setattr(address, field, address_data[field])
            address_changed = True
    if "bus_number" in address_data:
        address.bus_number = address_data["bus_number"] or None
        address_changed = True
    if "postal_code" in address_data and address_data["postal_code"]:
        postal_code = (
            db.query(PostalCode)
            .filter(PostalCode.postal_code == address_data["postal_code"])
            .first()
        )
        if postal_code is None:
            raise HouseholdRefused(
                _("Onbekende postcode: %(postal_code)s")
                % {"postal_code": address_data["postal_code"]}
            )
        address.postal_code_id = postal_code.id
        address_changed = True
    if address_changed:
        snapshot_address(
            db,
            address,
            operation="update",
            action="address_updated",
            source=SOURCE,
            actor=actor,
        )


def _upsert_contact(
    db: Session, target: Person, type_code: str, value: Optional[str], *, actor: Optional[str]
) -> None:
    from app.domains.audit.api import snapshot_contact_detail

    existing = next((c for c in target.contact_details if c.contact_type_code == type_code), None)
    if value:
        if existing is not None:
            if existing.value != value:
                existing.value = value
                db.flush()
                snapshot_contact_detail(
                    db,
                    existing,
                    operation="update",
                    action="contacts_updated",
                    source=SOURCE,
                    actor=actor,
                )
        else:
            contact = ContactDetail(
                person_id=target.id, contact_type_code=type_code, value=value, is_primary=True
            )
            target.contact_details.append(contact)
            db.flush()
            snapshot_contact_detail(
                db,
                contact,
                operation="insert",
                action="contacts_updated",
                source=SOURCE,
                actor=actor,
            )
    elif existing is not None:
        snapshot_contact_detail(
            db,
            existing,
            operation="delete",
            action="contacts_updated",
            source=SOURCE,
            actor=actor,
        )
        target.contact_details.remove(existing)


def add_household_person(
    db: Session, household: Member, data: dict, *, actor: Optional[str]
) -> Person:
    """Add a person to the household, as a child — the member never picks the
    relation type. No address: that belongs to the main member only (#125)."""
    person = insert_household_person(db, household, data, actor=actor)
    db.commit()
    db.refresh(person)
    return person


def insert_household_person(
    db: Session, household: Member, data: dict, *, actor: Optional[str]
) -> Person:
    """A new person of the household with the history rows, without committing
    (#1590: shared by `add_household_person` and the save of the whole household)."""
    from app.domains.audit.api import (
        snapshot_contact_detail,
        snapshot_member_person,
        snapshot_person,
    )
    from app.i18n import _

    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()
    if not first_name or not last_name:
        raise HouseholdRefused(_("Voornaam en achternaam zijn verplicht."))
    MemberPerson.require_details(data.get("date_of_birth"), data.get("gender_code"))

    person = Person(
        first_name=first_name,
        last_name=last_name,
        date_of_birth=data.get("date_of_birth") or None,
        gender_code=data.get("gender_code") or None,
    )
    db.add(person)
    db.flush()
    snapshot_person(
        db, person, operation="insert", action="person_created", source=SOURCE, actor=actor
    )

    link = MemberPerson(
        member_id=household.id, person_id=person.id, relation_type=RelationType.ADULT_CHILD
    )
    db.add(link)
    db.flush()
    snapshot_member_person(
        db,
        link,
        operation="insert",
        action="person_added_to_family",
        source=SOURCE,
        actor=actor,
    )

    for type_code, key in (("EMAIL", "email"), ("PHONE", "phone"), ("MOBILE", "mobile")):
        if data.get(key):
            contact = ContactDetail(
                person_id=person.id, contact_type_code=type_code, value=data[key], is_primary=True
            )
            db.add(contact)
            db.flush()
            snapshot_contact_detail(
                db,
                contact,
                operation="insert",
                action="contacts_updated",
                source=SOURCE,
                actor=actor,
            )
    return person


def remove_household_person(
    db: Session, household: Member, person_id: int, *, by: Person, actor: Optional[str]
) -> None:
    """Take a person out of the household — the link goes, the person stays.

    `by` is the member who acts: nobody removes themselves.
    """
    target = household_person(db, household, person_id)
    detach_household_person(db, household, target, by=by, actor=actor)
    db.commit()


def detach_household_person(
    db: Session, household: Member, target: Person, *, by: Person, actor: Optional[str]
) -> None:
    """Soft-delete this person's link to the household with its history row,
    without committing (#1590). Refuses the acting member themselves."""
    from app.domains.audit.api import snapshot_member_person
    from app.i18n import _

    if target.id == by.id:
        raise CannotRemoveSelf(_("Je kan jezelf niet uit het gezin verwijderen."))
    link = next((m for m in target.member_persons if m.member_id == household.id), None)
    if link is not None:
        snapshot_member_person(
            db,
            link,
            operation="delete",
            action="person_removed_from_family",
            source=SOURCE,
            actor=actor,
        )
        soft_delete(link)


def person_payload(person: Person) -> dict[str, Any]:
    """A person of the household as the portal's JSON shows it — the read that both
    the household view and every mutation answer with."""
    from app.domains.mdm.codes import CONTACT

    link = next((m for m in person.member_persons), None)
    contacts = {c.contact_type_code: c.value for c in person.contact_details}
    # #1174: every e-mail address, the main one first and then by id. `contacts`
    # above keeps one value per kind — good enough for phone and mobile, but a
    # member may hold several e-mail addresses and the portal manages that list.
    # The same shape as `FamilyMemberResponse.emails` on the admin screen, so the
    # two templates read the same.
    emails = [
        {"id": c.id, "value": c.value, "is_primary": bool(c.is_primary)}
        for c in sorted(
            (c for c in person.contact_details if c.contact_type_code == CONTACT.EMAIL and c.value),
            key=lambda c: (not c.is_primary, c.id or 0),
        )
    ]
    address = None
    if person.address:
        a = person.address
        postal_code = a.postal_code
        address = {
            "id": a.id,
            "street": a.street,
            "house_number": a.house_number,
            "bus_number": a.bus_number,
            "postal_code": postal_code.postal_code if postal_code else None,
            "municipality": postal_code.municipality if postal_code else None,
            "postal_code_id": a.postal_code_id,
        }
    return {
        "id": person.id,
        "emails": emails,
        "first_name": person.first_name,
        "last_name": person.last_name,
        "date_of_birth": person.date_of_birth.isoformat() if person.date_of_birth else None,
        "gender_code": person.gender_code,
        "relation_type": link.relation_type if link else None,
        # Decided here and not in the template: `relation_type` is a `RelationType`
        # member, so the template's `== "HOOFDLID"` was always false after CR-12
        # phase 2, and the main member lost the fields only a main member has.
        "is_main_member": bool(link and link.relation_type is RelationType.PRIMARY_MEMBER),
        "address": address,
        "email": contacts.get("EMAIL"),
        "phone": contacts.get("PHONE"),
        "mobile": contacts.get("MOBILE"),
    }
