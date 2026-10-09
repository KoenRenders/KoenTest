"""A household's persons, changed by a member of that household (CR-13 phase 3, #1250).

The household and its persons are master data (Koen, 27 September 2026: *"gezin en
personen is mdm"*); the membership — the yearly record, its payment, the renewal
window — is `membership`'s. Until this phase the family portal's mutations (change a
person, add one, remove one) were implemented in `membership/household_router.py`
and reached through `membership.api` functions that called the JSON router: a
second domain writing `mdm`'s rows. They live here now, behind `mdm.api`.

Since CR-13 phase 4b (#1251) the functions here do not commit: the JSON doors
for one person had no caller and went, with the three committing functions only
they called. What stays are the cores the one save of a household
(`household_save.py`, #1590) calls inside its one transaction.

Same behaviour as before the move (R13), including the order of the checks. The
refusals are `MasterDataError`s, one kind per answer the door gives, so no door has
to read a message to pick a status code.

Every write logs an audit row with `source="member_self"`; the actor is the
e-mail address of the member who acted, which the door knows and passes in.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.domains.mdm.codes import CONTACT
from app.domains.mdm.models import (
    MasterDataError,
    Member,
    MemberPerson,
    Person,
    PostalCode,
    RelationType,
)
from app.domains.mdm.service import new_contact_detail, require_email_free
from app.kernel.codes import code_of
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


class MainMemberStays(MasterDataError):
    """The main member cannot be taken out of the household (#1603)."""


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


def apply_person_fields(
    db: Session,
    target: Person,
    new: dict[str, Any],
    *,
    actor: Optional[str],
    details_required: bool = True,
) -> bool:
    """Write these person fields with their history, without committing (#1590:
    the save of the whole household and of one's own details call it).
    Returns whether anything changed."""
    from app.domains.mdm.history import snapshot_person

    # #681: judge the outcome — the portal does not always send every field — and
    # judge it before applying anything: a rollback after the change would also
    # throw away everything else in the same session.
    # `details_required=False`: Mijn gegevens (CR-22 S6a, #1710) writes a name
    # and asks neither birth date nor gender — those are the household's (R17).
    if details_required:
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


def _is_main_member(household: Member, person: Person) -> bool:
    return any(
        link.person_id == person.id
        and link.deleted_at is None
        and link.relation_type == RelationType.PRIMARY_MEMBER
        for link in household.member_persons
    )


def main_member(household: Member) -> Optional[Person]:
    """The household's main member, when it has one."""
    return next(
        (
            link.person
            for link in household.member_persons
            if link.deleted_at is None
            and link.relation_type == RelationType.PRIMARY_MEMBER
            and link.person is not None
        ),
        None,
    )


def household_address_holder(household: Member) -> Optional[Person]:
    """The person who holds the household's address, when it has one."""
    return next(
        (
            link.person
            for link in household.member_persons
            if link.deleted_at is None and link.person is not None and link.person.address
        ),
        None,
    )


#: The three things an address cannot do without, in the order a form asks them.
ADDRESS_REQUIRED = ("street", "house_number", "postal_code")


def require_whole_address(address_data: dict) -> None:
    """Street, house number and postal code, all three — or `HouseholdRefused`
    (#1603: required together as soon as one of them is filled)."""
    from app.i18n import _

    if any(not (address_data.get(name) or "").strip() for name in ADDRESS_REQUIRED):
        raise HouseholdRefused(
            _("Een adres heeft een straat, een huisnummer en een postcode nodig.")
        )


def _postal_code(db: Session, code: str) -> PostalCode:
    from app.i18n import _

    postal_code = db.query(PostalCode).filter(PostalCode.postal_code == code).first()
    if postal_code is None:
        raise HouseholdRefused(_("Onbekende postcode: %(postal_code)s") % {"postal_code": code})
    return postal_code


def apply_address(db: Session, target: Person, address_data: dict, *, actor: Optional[str]) -> None:
    """Write this person's address with its history row, without committing.

    - The person has one: the fields `address_data` names are changed
      (`address_updated`).
    - The person has none (#1603): the address is created, whole —
      street, house number and postal code together, or it is refused
      (`address_created`). The caller decides WHO may get one: the household's
      main member, when the household has no address yet.

    Refuses a postal code that is not in the table.
    """
    from app.domains.mdm.history import snapshot_address
    from app.domains.mdm.models import Address

    address = target.address
    if address is None:
        require_whole_address(address_data)
        address = Address(
            person_id=target.id,
            street=address_data["street"].strip(),
            house_number=address_data["house_number"].strip(),
            bus_number=(address_data.get("bus_number") or "").strip() or None,
            postal_code_id=_postal_code(db, address_data["postal_code"].strip()).id,
        )
        db.add(address)
        db.flush()
        db.refresh(target)
        operation, action, address_changed = "insert", "address_created", True
    else:
        operation, action, address_changed = "update", "address_updated", False
        for field in ("street", "house_number"):
            if field in address_data and address_data[field] is not None:
                setattr(address, field, address_data[field])
                address_changed = True
        if "bus_number" in address_data:
            address.bus_number = address_data["bus_number"] or None
            address_changed = True
        if "postal_code" in address_data and address_data["postal_code"]:
            address.postal_code_id = _postal_code(db, address_data["postal_code"]).id
            address_changed = True
    if address_changed:
        snapshot_address(
            db, address, operation=operation, action=action, source=SOURCE, actor=actor
        )


def _upsert_contact(
    db: Session, target: Person, type_code: str, value: Optional[str], *, actor: Optional[str]
) -> None:
    from app.domains.mdm.history import snapshot_contact_detail

    existing = next((c for c in target.contact_details if c.contact_type_code == type_code), None)
    if value:
        if existing is not None:
            if existing.value != value:
                # CR-22 (#1704): a changed address passes the rule a new one does.
                if code_of(type_code) == code_of(CONTACT.EMAIL):
                    require_email_free(db, target, value)
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
            contact = new_contact_detail(db, target, type_code, value, is_primary=True)
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


def default_relation(earlier: Sequence[object]) -> str:
    """The relation a new person in a household starts with (#1321): the stored code.

    Koen, 29 September 2026: *"Meestal werkt men zo: hoofdlid, partner,
    kinderen."* The first person is the head of household, the next one the
    partner as long as there is none yet, and everyone after that an (adult)
    child. Only the prefill: nothing is refused, a second partner stays possible.

    `earlier` are the relations of the persons before this one, as codes, in the
    order of the form. The one rule, for Word lid and for Mijn gezin (#1603): the
    page prefills a new person with it, and the server falls back on it for a
    person without a relation. It lived in `membership` until #1603; the
    household is master data, and both pages' saves need it.
    """
    # Tolerant of what a page sends: an unknown word is no partner.
    codes = [str(getattr(r, "value", r)) for r in earlier if r]
    if not codes:
        return RelationType.PRIMARY_MEMBER.value
    if RelationType.PARTNER.value not in codes:
        return RelationType.PARTNER.value
    return RelationType.ADULT_CHILD.value


#: What a member may choose for a person they add (#1603): never the main member.
ADDED_RELATIONS = (RelationType.PARTNER, RelationType.ADULT_CHILD)


def chosen_relation(asked: object, earlier: Sequence[object]) -> RelationType:
    """The relation of a person a member adds: what they chose — partner or
    child — or the one rule's default when they chose nothing.

    Refuses anything else, the main member first of all: a household has one,
    and it is the person who signed it up.
    """
    from app.i18n import _

    if not asked:
        return RelationType(default_relation(earlier))
    try:
        relation = RelationType(asked)
    except ValueError:
        relation = None
    if relation not in ADDED_RELATIONS:
        raise HouseholdRefused(_("Kies partner of kind."))
    return relation


def household_relations(household: Member) -> list[str]:
    """The relations the household holds now, in its own order."""
    links = sorted(
        (m for m in household.member_persons if m.deleted_at is None),
        key=MemberPerson.household_position,
    )
    return [RelationType(m.relation_type).value for m in links]


def insert_household_person(
    db: Session, household: Member, data: dict, *, actor: Optional[str]
) -> Person:
    """A new person of the household with the history rows, without committing
    (#1590): a partner while the household has none, otherwise a child, or what
    the caller chose of those two (`relation_type`, #1603). No address: that
    belongs to the main member only (#125)."""
    from app.domains.mdm.history import (
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
    relation = chosen_relation(data.get("relation_type"), household_relations(household))

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

    link = MemberPerson(member_id=household.id, person_id=person.id, relation_type=relation)
    # Through the household, so the next person added in the same save sees this
    # one: a partner, and after that a child.
    household.member_persons.append(link)
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
            contact = new_contact_detail(db, person, type_code, data[key], is_primary=True)
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


def detach_household_person(
    db: Session,
    household: Member,
    target: Person,
    *,
    by: Optional[Person],
    actor: Optional[str],
    source: str = SOURCE,
) -> None:
    """Soft-delete this person's link to the household with its history row,
    without committing (#1590). Refuses the acting member themselves, and the
    main member whoever asks (#1603) — here, so every door refuses.

    `by` is the member who acts; the board has no person and passes None
    (CR-22 S7, #1712) — then only the refusal of oneself falls away. `source`
    is what the history row says: the member's own act, or the board's."""
    from app.domains.mdm.history import snapshot_member_person
    from app.i18n import _

    if by is not None and target.id == by.id:
        raise CannotRemoveSelf(_("Je kan jezelf niet uit het gezin verwijderen."))
    if _is_main_member(household, target):
        raise MainMemberStays(_("Een gezin heeft een hoofdlid nodig."))
    link = next((m for m in target.member_persons if m.member_id == household.id), None)
    if link is not None:
        snapshot_member_person(
            db,
            link,
            operation="delete",
            action="person_removed_from_family",
            source=source,
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
        {
            "id": c.id,
            "value": c.value,
            "is_primary": bool(c.is_primary),
            # CR-22 R15 (#1711): False while the address waits for its code.
            "confirmed": c.confirmed_at is not None,
        }
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
