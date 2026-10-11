"""The one save of a household — by a member of it (CR-11 pilot B, #1590) and by
the board on the household's record (#1899).

**Two callers, one function.** `by` is the member who acts, or None for the
board, who is no person of the household. What differs is said here and
nowhere else:

- the history says `member_self` for the member and the board's source for
  the board, each with its own actor;
- an e-mail address a member types waits for its code (CR-22 R15); one the
  board types counts at once;
- a person a member takes out leaves the household and stays a person; one
  the board takes out is deleted (`mdm.delete_person`, #1712) — what its own
  door did;
- the board also says which board member follows the household, and may hand
  in what another domain writes in the same transaction (`also`: the
  membership years the record removes).

Everything else — the fields, the refusals and where they stand, the relation
of a person who is already there (partner or child, never the main member) —
is one rule for both.

What follows is the history of the member's save.

The household's portal page edits as a whole — its persons, their e-mail
addresses and the address — and one "Opslaan" writes them in **one transaction**.
Until #1590 every person had a form of its own, and saving one person was two
transactions (the person, then the e-mail rows): a refusal in the second left the
first stored.

`save_household` writes nothing the row functions did not write and refuses
everything they refused: it calls the non-committing cores
(`household_service.apply_person_fields`, `insert_household_person`,
`detach_household_person`, `apply_address`; `service.write_email_rows`,
`promote_email_row`) that the committing doors of the JSON API called until
those went with CR-13 phase 4b (#1251). What was new is said where it stands:

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

from collections.abc import Callable
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
    #: Partner or child: what was chosen for a person who is added ("" is the
    #: one rule's default), and the relation a person who is already there gets
    #: (#1899; "" leaves it alone — the main member's card sends none).
    relation_type: str = ""
    #: The e-mail rows that say something: an address, or a stored row (emptied
    #: means removed). An empty row that was never stored is not among them —
    #: the reader of the form leaves it out (#1641).
    emails: list[EmailRow] = field(default_factory=list)
    #: The field of the person's first e-mail row as the form sent it, empty or
    #: not ("" when the form sent none): where "an address is asked" is said.
    email_field: str = ""


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


#: What the history says of a change the board makes on the household's record —
#: the source its eleven partial doors wrote until #1899. Stored data.
BOARD_UPDATE = "admin_update"

#: Passed as `board_member` when the form carries none: it is left alone.
UNCHANGED: Any = object()


def save_household(
    db: Session,
    household: Member,
    payload: HouseholdSave,
    *,
    by: Optional[Person],
    actor: Optional[str],
    board_member: Any = UNCHANGED,
    also: Optional[Callable[[Session], None]] = None,
) -> Member:
    """Write the whole household in one transaction; `HouseholdSaveRefused` with
    nothing written when any part is refused.

    `by` is the member who acts, None for the board (the module's docstring says
    what that changes). `board_member`: the id of the board member who follows
    the household, or None for nobody. `also` writes what is another domain's
    in this same transaction, without committing; what it raises rolls the
    whole save back."""
    from app.domains.mdm.service import delete_person

    board = by is None
    source = BOARD_UPDATE if board else hs.SOURCE
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
                    if board:
                        delete_person(db, person, actor=actor)
                    else:
                        hs.detach_household_person(db, household, person, by=by, actor=actor)
        for row in payload.persons:
            _save_person(db, household, existing, row, actor, errors, source, board)
        if payload.address is not None:
            _save_address(db, household, payload.address, actor, errors, source)
        if board_member is not UNCHANGED:
            with errors.at("board_member"):
                hs.apply_board_member(db, household, board_member, actor=actor, source=source)
        if also is not None and not errors.found:
            also(db)
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


def save_person(
    db: Session,
    person: Person,
    rows: list[PersonRow],
    *,
    actor: Optional[str],
    errors: Optional[list[FieldError]] = None,
) -> Person:
    """Write ONE person's own details — name, birth date, gender, mobile and
    telephone number, e-mail rows — in one transaction (Mijn gegevens, CR-22
    S6a, #1710; #1899); `HouseholdSaveRefused` with nothing written when any
    part is refused.

    The same helpers as the household's save, so a change here is the change
    Mijn gezin would make. Birth date and gender are asked of a person in a
    household and not of an account alone (CR-22 R17 as corrected on 10
    October 2026). Not touched: the relation and the address. `rows` is what
    the form carried: exactly this person, or the save is refused."""
    from app.i18n import _

    savepoint = db.begin_nested()
    found = Refusals(list(errors or []), kinds=(MasterDataError,), passing=(HouseholdSaveRefused,))
    try:
        if len(rows) != 1 or rows[0].key != str(person.id):
            found.add(
                "",
                _("Je kan alleen je eigen gegevens bewaren. Herlaad de pagina en probeer opnieuw."),
            )
            raise HouseholdSaveRefused(found.found)
        row = rows[0]
        at = f"h.{row.key}"
        _storable(db, row, at, found)
        if found.found:
            raise HouseholdSaveRefused(found.found)
        in_household = any(link.deleted_at is None for link in person.member_persons)
        values: dict[str, Any] = {
            "first_name": row.first_name.strip(),
            "last_name": row.last_name.strip(),
            "date_of_birth": row.date_of_birth,
            "gender_code": row.gender_code or None,
        }
        asked = ("date_of_birth", "gender_code") if in_household else ()
        missing = _first_missing(row, (*asked, "first_name", "last_name"))
        with found.at(f"{at}.{missing}" if missing else at):
            hs.apply_person_fields(db, person, values, actor=actor, details_required=in_household)
        if not found.touches(at):
            for type_code, value in (("PHONE", row.phone), ("MOBILE", row.mobile)):
                hs._upsert_contact(db, person, type_code, value.strip(), actor=actor)
            _save_emails(db, person, row, actor, found, hs.SOURCE, False)
        if found.found:
            raise HouseholdSaveRefused(found.found)
        with found.at(""):
            db.flush()
        if found.found:
            raise HouseholdSaveRefused(found.found)
    except Exception:
        try:
            savepoint.rollback()
        except InvalidRequestError:
            pass  # already closed
        raise
    savepoint.commit()
    db.commit()
    db.refresh(person)
    return person


def _storable(db: Session, row: PersonRow, at: str, errors: Refusals) -> None:
    """What a person's columns cannot hold is refused at its field, before the
    write (`require_storable_person`): a name longer than its column, a gender
    that is not of the list. Asked here for both callers since #1899 — the
    board's doors asked it, and a member's save let the database refuse (a
    500)."""
    for name in ("first_name", "last_name"):
        with errors.at(f"{at}.{name}"):
            hs.require_storable_person(db, getattr(row, name).strip(), "", None)
    with errors.at(f"{at}.gender_code"):
        hs.require_storable_person(db, "", "", row.gender_code or None)


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
    source: str,
    board: bool,
) -> None:
    at = f"h.{row.key}"
    if errors.touches(at):
        return
    _storable(db, row, at, errors)
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
            hs.apply_person_fields(db, person, values, actor=actor, source=source)
        # #1899: the relation of a person who is already there — partner or
        # child, at its own field; the main member's card sends none.
        if row.relation_type and not errors.touches(at):
            with errors.at(f"{at}.relation_type"):
                hs.apply_relation(
                    db, household, person, row.relation_type, actor=actor, source=source
                )
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
            added = hs.insert_household_person(db, household, values, actor=actor, source=source)
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
        hs._upsert_contact(db, person, type_code, value.strip(), actor=actor, source=source)
    _save_emails(db, person, row, actor, errors, source, board)


def _save_emails(
    db: Session,
    person: Person,
    row: PersonRow,
    actor: Optional[str],
    errors: Refusals,
    source: str,
    confirmed: bool,
) -> None:
    """The person's e-mail rows: what the form holds is what stays. A row the
    form no longer has goes (as an emptied one always did); the primary mark
    moves only when the form marks another row.

    A row whose text is no address is refused at its own field, before any row
    of this person is written (#1853): the contact detail holds that rule at the
    flush, and asked here it has a place the screen can mark."""
    from app.domains.mdm.models import require_email_address
    from app.domains.mdm.service import promote_email_row, require_email_free, write_email_rows

    refused = False
    for given in row.emails:
        if not given.value.strip():
            continue
        place = f"e.{given.key}.value"
        with errors.at(place):
            require_email_address(given.value.strip())
            # An address that counts at once (the board's) claims its person at
            # once: someone else's is refused here, at its row (#1704, #1899). A
            # member's own waits for its code and is asked there.
            if confirmed:
                require_email_free(db, person, given.value.strip())
        refused = refused or errors.touches(place)
    if refused:
        return

    mine = {c.id for c in person.contact_details if c.contact_type_code == CONTACT.EMAIL}
    sent = {int(e.key): e.value.strip() for e in row.emails if e.key.isdigit()}
    texts = {row_id: sent.get(row_id, "") for row_id in mine}
    new = [e.value.strip() for e in row.emails if not e.key.isdigit()]
    # An address the person types himself waits for its code (CR-22 R15,
    # #1711); one the board types counts at once (`confirmed`).
    # The row the form marks as the primary one. When that is an address typed
    # in this save it waits, and the mark waits with it — carried out at its
    # code (#1590: adding an address and making it the main one is one save).
    chosen = next((e for e in row.emails if e.primary and e.value.strip()), None)
    write_email_rows(
        db,
        person,
        texts,
        new,
        actor=actor,
        source=source,
        confirmed=confirmed,
        primary_wanted=chosen.value.strip() if chosen is not None else "",
    )
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
    # A waiting address cannot be made the primary one: it is not proven yet.
    if target is not None and not target.is_primary and target.confirmed_at is not None:
        promote_email_row(db, person, target, actor=actor, source=source)


def _save_address(
    db: Session,
    household: Member,
    row: AddressRow,
    actor: Optional[str],
    errors: Refusals,
    source: str,
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
            # No main member to hang it on. A household that holds nobody says so
            # (the board's record can meet one, #1899); one whose persons carry no
            # main member is nothing this page can repair.
            if not _people(household):
                from app.i18n import _

                errors.add("address.street", _("Gezin zonder personen."))
            return
        with errors.at(f"address.{missing or 'postal_code'}"):
            hs.apply_address(db, target, sent, actor=actor, source=source)
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
        hs.apply_address(db, holder, changed, actor=actor, source=source)
