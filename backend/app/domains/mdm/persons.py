"""Personen — every natural person in master data, for the board (CR-22 S7,
#1712; R18).

One list: name, main e-mail address, mobile number, the household (or none)
and when the person was made; a person without a household whose address is
confirmed is an account (CR-22 §B1 D1). Three views — *Zonder gezin* (the default),
*In een gezin*, *Alle* — and a search on the name or an e-mail address.
Nothing is edited here: a person manages himself, a household's data stays in
the household. The one action is deleting, `service.delete_person`.

"In a household" is what it means everywhere: a `MemberPerson` row, whatever
the relation (`service.is_member`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.domains.mdm.codes import CONTACT
from app.domains.mdm.models import ContactDetail, Member, MemberPerson, Person, RelationType

#: The views, by their value in the address (a path a person sees: Dutch).
WITHOUT_HOUSEHOLD = "zonder"
IN_HOUSEHOLD = "in"
EVERYONE = "alle"
VIEWS = (WITHOUT_HOUSEHOLD, IN_HOUSEHOLD, EVERYONE)

_LIKE_SPECIAL = str.maketrans({"\\": "\\\\", "%": "\\%", "_": "\\_"})


@dataclass(frozen=True)
class PersonRow:
    """One person as the list shows him."""

    id: int
    name: str
    email: Optional[str]
    mobile: Optional[str]
    household_id: Optional[int]
    household_name: Optional[str]
    is_main_member: bool
    #: CR-22 D1: no household and a confirmed e-mail address — he can sign in.
    is_account: bool
    created_at: datetime


@dataclass(frozen=True)
class PersonsPage:
    rows: list[PersonRow]
    total: int
    counts: dict[str, int]


def view_from(value: object) -> str:
    """The view an address asks for; anything else is the default."""
    return value if value in VIEWS else WITHOUT_HOUSEHOLD


def household_name(household: Member) -> str:
    """A household is called by its main member, "last name first name" — as
    the members list calls it. Reads what is loaded."""
    links = [m for m in household.member_persons if m.deleted_at is None]
    main = next((m for m in links if m.relation_type == RelationType.PRIMARY_MEMBER), None)
    link = main or next(iter(sorted(links, key=MemberPerson.household_position)), None)
    if link is None or link.person is None:
        return f"#{household.id}"
    return f"{link.person.last_name} {link.person.first_name}"


def _in_household():
    """The person stands in a household link that is not deleted. The link's own
    `deleted_at` is named: a subquery is not an entity the soft-delete filter
    reaches."""
    return Person.id.in_(select(MemberPerson.person_id).where(MemberPerson.deleted_at.is_(None)))


def _searched(query, q: str):
    needle = (q or "").strip().lower()
    if not needle:
        return query
    pattern = f"%{needle.translate(_LIKE_SPECIAL)}%"
    with_address = select(ContactDetail.person_id).where(
        ContactDetail.deleted_at.is_(None),
        ContactDetail.contact_type_code == CONTACT.EMAIL,
        func.lower(ContactDetail.value).like(pattern, escape="\\"),
    )
    return query.filter(
        or_(
            func.lower(Person.first_name + " " + Person.last_name).like(pattern, escape="\\"),
            func.lower(Person.last_name + " " + Person.first_name).like(pattern, escape="\\"),
            Person.id.in_(with_address),
        )
    )


def _viewed(query, view: str):
    if view == WITHOUT_HOUSEHOLD:
        return query.filter(~_in_household())
    if view == IN_HOUSEHOLD:
        return query.filter(_in_household())
    return query


def _row(person: Person) -> PersonRow:
    contacts = [c for c in person.contact_details if c.deleted_at is None and c.value]
    emails = sorted(
        (c for c in contacts if c.contact_type_code == CONTACT.EMAIL),
        key=lambda c: (not c.is_primary, c.id or 0),
    )
    mobile = next((c.value for c in contacts if c.contact_type_code == CONTACT.MOBILE), None)
    link = next(
        iter(
            sorted(
                (m for m in person.member_persons if m.deleted_at is None),
                key=lambda m: m.member_id,
            )
        ),
        None,
    )
    household = link.member if link is not None else None
    return PersonRow(
        id=person.id,
        name=f"{person.first_name} {person.last_name}",
        email=emails[0].value if emails else None,
        mobile=mobile,
        household_id=household.id if household is not None else None,
        household_name=household_name(household) if household is not None else None,
        is_main_member=link is not None and link.relation_type == RelationType.PRIMARY_MEMBER,
        is_account=link is None and any(c.confirmed_at is not None for c in emails),
        created_at=person.created_at,
    )


def persons_page(
    db: Session, *, view: str = WITHOUT_HOUSEHOLD, q: str = "", page: int = 1, per_page: int = 50
) -> PersonsPage:
    """One page of the list, by last name, first name and id; with the number of
    persons per view for what was searched — the search cuts every count, the
    view cuts only the list."""
    searched = _searched(db.query(Person), q)
    counts = {v: _viewed(searched, v).count() for v in VIEWS}
    total = counts[view]
    last_page = max(1, -(-total // per_page))
    page = min(max(1, page), last_page)
    persons = (
        _viewed(searched, view)
        .order_by(Person.last_name, Person.first_name, Person.id)
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )
    return PersonsPage(rows=[_row(p) for p in persons], total=total, counts=counts)


def person_row(db: Session, person_id: int) -> Optional[PersonRow]:
    """One person as the list shows him, or None when he is not there."""
    person = db.query(Person).filter(Person.id == person_id).first()
    return _row(person) if person is not None else None


def delete_listed_person(db: Session, person_id: int, *, actor: Optional[str]) -> None:
    """The list's one action: find the person and hand him to THE delete
    (`service.delete_person`), whose refusals pass through."""
    from app.domains.mdm.service import delete_person

    person = db.query(Person).filter(Person.id == person_id).first()
    if person is not None:
        delete_person(db, person, actor=actor)
        db.commit()
