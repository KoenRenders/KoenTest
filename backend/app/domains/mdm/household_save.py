"""The one save of a household, by a member of it (CR-11 pilot B, #1590).

The household's portal page edits as a whole — its persons, their e-mail
addresses and the address — and one "Opslaan" writes them in **one transaction**.
Until #1590 every person had a form of its own, and saving one person was two
transactions (the person, then the e-mail rows): a refusal in the second left the
first stored.

`save_household` writes nothing the row functions did not write and refuses
everything they refused: it calls the same non-committing cores
(`household_service.apply_person_fields`, `insert_household_person`,
`detach_household_person`, `apply_address`; `service.write_email_rows`,
`promote_email_row`) that the committing doors — still used by the JSON API —
call. What is new is said where it stands:

- every refusal comes back at once, each at its place (`kernel.refusals`): a
  field (`h.<key>.first_name`, `e.<key>.value`, `address.postal_code`), a row
  (`h.<key>`, also a row the form removed), or the household as a whole;
- a row that did not change is not written and gets no history row;
- the e-mail history of a member's own save says `member_self` (the row
  functions wrote `admin_update` for the member too);
- a birth date that is no date is refused at its field (it was a 500).

A refusal anywhere rolls the whole save back: nothing is half written.

The rules that are a choice for Koen (may the main member be removed, which
relation a new person gets, may the primary address go, may an address be
created) are NOT decided here: this keeps what holds today on every one of them.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Optional

from sqlalchemy.exc import InvalidRequestError
from sqlalchemy.orm import Session

from app.domains.mdm import household_service as hs
from app.domains.mdm.codes import CONTACT
from app.domains.mdm.models import MasterDataError, Member, Person
from app.kernel.refusals import FieldError, Refusals

#: The fields of a person the save compares and writes.
PERSON_FIELDS = ("first_name", "last_name", "date_of_birth", "gender_code")
ADDRESS_FIELDS = ("street", "house_number", "bus_number", "postal_code")


@dataclass
class EmailRow:
    """One e-mail address of a person. `key` is the row's id, or anything else
    for a row added in the page."""

    key: str
    value: str = ""
    #: The form marks this row as the person's primary address.
    primary: bool = False


@dataclass
class PersonRow:
    """One person of the household. `key` is the person's id, or anything else
    for a person added in the page."""

    key: str
    first_name: str = ""
    last_name: str = ""
    #: None when the form's value was empty — or no date, and then the row
    #: carries an error.
    date_of_birth: Optional[date] = None
    gender_code: Optional[str] = None
    phone: str = ""
    mobile: str = ""
    #: What the member chose for a person they add: partner or child, or "" for
    #: the one rule's default. Not read for a person who is already there.
    relation_type: str = ""
    emails: list[EmailRow] = field(default_factory=list)


@dataclass
class AddressRow:
    street: str = ""
    house_number: str = ""
    bus_number: str = ""
    postal_code: str = ""


@dataclass
class HouseholdSave:
    """Everything one "Opslaan" of the household carries."""

    persons: list[PersonRow] = field(default_factory=list)
    #: None: the form carried no address, and it is left alone.
    address: Optional[AddressRow] = None
    #: What the form's reader already refused (a date that is no date).
    errors: list[FieldError] = field(default_factory=list)


class HouseholdSaveRefused(MasterDataError):
    """The save is refused; `errors` says why and where, all of them."""

    def __init__(self, errors: list[FieldError]) -> None:
        self.errors = list(errors)
        super().__init__(" ".join(error.message for error in self.errors))


def _people(household: Member) -> dict[str, Person]:
    """The persons of the household, by their id as the form writes it."""
    return {
        str(link.person_id): link.person
        for link in household.member_persons
        if link.deleted_at is None and link.person is not None
    }


def save_household(
    db: Session,
    household: Member,
    payload: HouseholdSave,
    *,
    by: Person,
    actor: Optional[str],
) -> Member:
    """Write the whole household in one transaction; `HouseholdSaveRefused` with
    nothing written when any part is refused. `by` is the member who acts."""
    # A savepoint around the whole save: a refusal takes back exactly what this
    # save wrote and nothing else, and the session stays usable for the answer
    # that says why.
    savepoint = db.begin_nested()
    errors = Refusals(payload.errors, kinds=(MasterDataError,), passing=(HouseholdSaveRefused,))
    try:
        existing = _people(household)
        kept = {row.key for row in payload.persons}
        # Removals first: a refusal names its row before anything is added. Its
        # place is the row the form removed, so the screen can put it back.
        for key, person in existing.items():
            if key not in kept:
                with errors.at(f"h.{key}"):
                    hs.detach_household_person(db, household, person, by=by, actor=actor)
        for row in payload.persons:
            _save_person(db, household, existing, row, actor, errors)
        if payload.address is not None:
            _save_address(db, household, payload.address, actor, errors)
        if errors.found:
            raise HouseholdSaveRefused(errors.found)
        with errors.at(""):
            db.flush()  # the object rules fire here once more, at the write itself
        if errors.found:
            raise HouseholdSaveRefused(errors.found)
    except Exception:
        # Also after a failed flush: the savepoint is then deactivated, not closed,
        # and the session refuses everything until it is rolled back.
        try:
            savepoint.rollback()
        except InvalidRequestError:
            pass  # already closed
        raise
    savepoint.commit()
    db.commit()
    db.refresh(household)
    return household


def _first_missing(row: PersonRow, order: tuple[str, ...]) -> str:
    """The field the person rules refuse first, in the order they ask — so the
    one message they give stands at the field it is about."""
    for name in order:
        value = getattr(row, name)
        if value is None or (isinstance(value, str) and not value.strip()):
            return name
    return ""


def _save_person(
    db: Session,
    household: Member,
    existing: dict[str, Person],
    row: PersonRow,
    actor: Optional[str],
    errors: Refusals,
) -> None:
    at = f"h.{row.key}"
    if errors.touches(at):
        return
    values: dict[str, Any] = {
        "first_name": row.first_name.strip(),
        "last_name": row.last_name.strip(),
        "date_of_birth": row.date_of_birth,
        "gender_code": row.gender_code or None,
    }
    if row.key in existing:
        person = existing[row.key]
        # `apply_person_fields` asks birth date and gender first (#681), then the
        # object refuses a blank name as it is set.
        missing = _first_missing(row, ("date_of_birth", "gender_code", "first_name", "last_name"))
        with errors.at(f"{at}.{missing}" if missing else at):
            hs.apply_person_fields(db, person, values, actor=actor)
    elif row.key.isdigit():
        from app.i18n import _

        errors.add(
            at,
            _("Deze persoon hoort niet meer bij het gezin. Herlaad de pagina en probeer opnieuw."),
        )
        return
    else:
        # The relation first, at its own field (#1603): partner or child, never
        # the main member; nothing chosen is the one rule's default.
        with errors.at(f"{at}.relation_type"):
            hs.chosen_relation(row.relation_type, hs.household_relations(household))
        if errors.touches(at):
            return
        values["relation_type"] = row.relation_type
        # `insert_household_person` asks the names first, then birth date and gender.
        missing = _first_missing(row, ("first_name", "last_name", "date_of_birth", "gender_code"))
        added = None
        with errors.at(f"{at}.{missing}" if missing else at):
            added = hs.insert_household_person(db, household, values, actor=actor)
        if added is None:
            return
        person = added
    if errors.touches(at):
        return
    # The main member's mobile number is not asked here (Koen, 5 October 2026,
    # #1603): with one save for the whole household the requirement blocked every
    # change of the ten households in a hundred whose main member has none. Word
    # lid still asks it.
    for type_code, value in (("PHONE", row.phone), ("MOBILE", row.mobile)):
        hs._upsert_contact(db, person, type_code, value.strip(), actor=actor)
    _save_emails(db, person, row, actor)


def _save_emails(db: Session, person: Person, row: PersonRow, actor: Optional[str]) -> None:
    """The person's e-mail rows: what the form holds is what stays. A row the
    form no longer has goes (as an emptied one always did); the primary mark
    moves only when the form marks another row."""
    from app.domains.mdm.service import promote_email_row, write_email_rows

    mine = {c.id for c in person.contact_details if c.contact_type_code == CONTACT.EMAIL}
    sent = {int(e.key): e.value.strip() for e in row.emails if e.key.isdigit()}
    texts = {row_id: sent.get(row_id, "") for row_id in mine}
    new = [e.value.strip() for e in row.emails if not e.key.isdigit()]
    write_email_rows(db, person, texts, new, actor=actor, source=hs.SOURCE)

    chosen = next((e for e in row.emails if e.primary and e.value.strip()), None)
    if chosen is None:
        return
    target = next(
        (
            c
            for c in person.contact_details
            if c.contact_type_code == CONTACT.EMAIL
            and (
                (chosen.key.isdigit() and c.id == int(chosen.key))
                or (
                    not chosen.key.isdigit()
                    and (c.value or "").lower() == chosen.value.strip().lower()
                )
            )
        ),
        None,
    )
    if target is not None and not target.is_primary:
        promote_email_row(db, person, target, actor=actor, source=hs.SOURCE)


def _save_address(
    db: Session,
    household: Member,
    row: AddressRow,
    actor: Optional[str],
    errors: Refusals,
) -> None:
    """The household's one address (#1603).

    - It has none and the form's fields are all empty: it stays without.
    - It has none and something is filled in: the address is created on the main
      member — street, house number and postal code together, or it is refused at
      the first of them that is missing.
    - It has one: only the fields that differ are written; emptying one of the
      three is refused the same way (an address is whole or it is not there, and
      taking it away is not something this page does).
    """
    sent = {name: getattr(row, name).strip() for name in ADDRESS_FIELDS}
    holder = hs.household_address_holder(household)
    missing = next((name for name in hs.ADDRESS_REQUIRED if not sent[name]), "")
    if holder is None:
        if not any(sent.values()):
            return
        target = hs.main_member(household)
        if target is None:
            return  # no main member to hang it on; nothing this page can repair
        with errors.at(f"address.{missing or 'postal_code'}"):
            hs.apply_address(db, target, sent, actor=actor)
        return
    address = holder.address
    current = {
        "street": address.street or "",
        "house_number": address.house_number or "",
        "bus_number": address.bus_number or "",
        "postal_code": address.postal_code.postal_code if address.postal_code else "",
    }
    changed = {name: sent[name] for name in ADDRESS_FIELDS if sent[name] != current[name]}
    if not changed:
        return
    with errors.at(f"address.{missing or 'postal_code'}"):
        hs.require_whole_address(sent)
        hs.apply_address(db, holder, changed, actor=actor)
