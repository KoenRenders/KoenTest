"""Identificatie van een lid op basis van zijn e-mailadres.

Een lid heeft (anders dan een admin) geen User-account. We herkennen het lid
aan de aanwezigheid van zijn e-mailadres als ContactDetail (type EMAIL) op een
Person, en lossen van daaruit het gezin (Member) op via MemberPerson.

De regel bij meerdere treffers (bevestigd in #80):
  - alle treffers in hetzelfde gezin  -> inloggen op dat gezin
    (bij voorkeur de hoofdlid-persoon),
  - treffers in verschillende gezinnen -> weigeren, want we mogen niet gokken.
"""

from typing import List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.mdm.api import CONTACT, ContactDetail, Person, RelationType


def find_persons_by_email(db: Session, email: str) -> List[Person]:
    """Alle personen met dit e-mailadres als EMAIL-contactgegeven (case-insensitief).

    Only a CONFIRMED address counts (CR-22 §B1 D3, F6; #1707): an address is the
    key someone signs in with, so it opens nothing until its owner has entered
    the code that was sent to it. A row that still waits is invisible here.
    """
    return (
        db.query(Person)
        .join(ContactDetail, ContactDetail.person_id == Person.id)
        .filter(
            ContactDetail.contact_type_code == CONTACT.EMAIL,
            ContactDetail.confirmed_at.isnot(None),
            func.lower(ContactDetail.value) == email.strip().lower(),
        )
        .all()
    )


def resolve_household(db: Session, persons: List[Person]) -> Tuple[str, Optional[int]]:
    """Bepaal het gezin voor een set personen.

    Retourneert ("ok", member_id), ("none", None) of ("multiple", None).
    """
    if not persons:
        return ("none", None)
    member_ids = {mp.member_id for p in persons for mp in p.member_persons}
    if not member_ids:
        return ("none", None)
    if len(member_ids) > 1:
        return ("multiple", None)
    return ("ok", next(iter(member_ids)))


#: What an address is, to whoever asks for a sign-in code (CR-22, #1707).
HOUSEHOLD = "ok"  # every holder in one household — the word `resolve_household` uses
ACCOUNT = "account"  # one person, in no household
MULTIPLE = "multiple"  # more than one answer: we do not guess
UNKNOWN = "none"


def sign_in_identity(db: Session, email: str) -> Tuple[str, Optional[Person]]:
    """Who an e-mail address signs in as: `(status, person)` (CR-22 F1, #1707).

    Everyone who signs in has an account — a person in master data:

    - every holder of the address in ONE household → `HOUSEHOLD`, and the
      person is the main member **when he holds the address himself**, else
      the first holder. A shared household address signs in as the main member
      (R21: the household acts as one); a partner with an address of his own
      signs in as himself.
    - exactly one holder, in no household → `ACCOUNT`, that person (R13).
    - holders in several households, several persons without a household, or
      a household member beside someone without one → `MULTIPLE`, no person:
      the address does not say who signs in. Master data refuses new cases
      (`mdm.service.email_refusal`); the ones that existed before stand.
    - nobody → `UNKNOWN`.
    """
    persons = find_persons_by_email(db, email)
    if not persons:
        return UNKNOWN, None
    without_household = [p for p in persons if not p.member_persons]
    status, member_id = resolve_household(db, persons)
    if not without_household:
        if status != "ok":
            return MULTIPLE, None
        for p in persons:
            if any(
                mp.member_id == member_id and mp.relation_type == RelationType.PRIMARY_MEMBER
                for mp in p.member_persons
            ):
                return HOUSEHOLD, p
        return HOUSEHOLD, persons[0]
    if len(persons) == 1:
        return ACCOUNT, persons[0]
    return MULTIPLE, None


def login_person_for_email(db: Session, email: str) -> Optional[Person]:
    """The person an e-mail address signs in as, or None — the one place every
    reader of "who is signed in" asks (CR-22 C1: nine callers).

    A member of a household, as before, and since CR-22 a person without a
    household too: an account. None when the address is unknown, still waits
    for its confirmation, or does not say who signs in (`sign_in_identity`).
    """
    return sign_in_identity(db, email)[1]


def has_household(person: Optional[Person]) -> bool:
    """Is this signed-in person a member of a household? An account is a person
    too since CR-22, so "there is a person" no longer means "Mijn gezin exists"
    (#1707): whoever shows or opens the household asks this."""
    return bool(person is not None and person.member_persons)
