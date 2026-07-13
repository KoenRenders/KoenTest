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

from app.models.member import Person, MemberPerson
from app.models.contact import ContactDetail


def find_persons_by_email(db: Session, email: str) -> List[Person]:
    """Alle personen met dit e-mailadres als EMAIL-contactgegeven (case-insensitief)."""
    return (
        db.query(Person)
        .join(ContactDetail, ContactDetail.person_id == Person.id)
        .filter(
            ContactDetail.contact_type_code == "EMAIL",
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
    member_ids = {
        mp.member_id
        for p in persons
        for mp in p.member_persons
    }
    if not member_ids:
        return ("none", None)
    if len(member_ids) > 1:
        return ("multiple", None)
    return ("ok", next(iter(member_ids)))


def login_person_for_email(db: Session, email: str) -> Optional[Person]:
    """De Person waarmee een geldig lid-token zich aanmeldt.

    Alleen geldig als alle treffers in één gezin zitten. Kiest bij voorkeur de
    hoofdlid-persoon van dat gezin, anders de eerste treffer. Geeft None terug
    als er geen of meerdere gezinnen zijn (we gokken niet).
    """
    persons = find_persons_by_email(db, email)
    status, member_id = resolve_household(db, persons)
    if status != "ok":
        return None
    for p in persons:
        if any(mp.member_id == member_id and mp.relation_type == "HOOFDLID" for mp in p.member_persons):
            return p
    return persons[0]
