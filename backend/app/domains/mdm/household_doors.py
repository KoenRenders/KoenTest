"""What a refusal of the household service answers at a door (CR-13 phase 3, #1250).

The service raises one kind of `MasterDataError` per answer; the doors — the
portal's JSON routes and its screen routes, and `membership`'s household view and
renewal — turn it into the status code the routes gave when the rules were theirs.
One table, so the doors cannot drift apart.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from fastapi import HTTPException

from app.domains.mdm.household_service import (
    CannotRemoveSelf,
    HouseholdNotFound,
    HouseholdRefused,
    MainMemberStays,
    OutsideHousehold,
    PersonNotFound,
)
from app.domains.mdm.models import EmailAddressInUse, MasterDataError, PersonDetailsMissing

STATUS = {
    HouseholdNotFound: 404,
    PersonNotFound: 404,
    OutsideHousehold: 403,
    CannotRemoveSelf: 400,
    MainMemberStays: 400,
    HouseholdRefused: 422,
    PersonDetailsMissing: 422,
}


@contextmanager
def household_refusals_as_http() -> Iterator[None]:
    """A refusal of the household service becomes the status code of this door."""
    try:
        yield
    except MasterDataError as refusal:
        status = STATUS.get(type(refusal))
        if status is None:
            raise
        raise HTTPException(status_code=status, detail=str(refusal)) from refusal


def says_why_in(line: str):
    """A refusal of this route goes to the message line of ITS card (#1831): the
    kit's `says_why_in`, with mdm's own refusal beside the status codes — an
    address in use, which the application answers as a JSON 422 for every other
    door (`main.py`)."""
    from app.ui import says_why_in as kit_says_why_in

    return kit_says_why_in(line, EmailAddressInUse)


def schema_refusal_words(refusal) -> str | None:
    """What a screen says when a request schema refuses a form of a household — one
    table for the Leden screen's cards, "Nieuw lid" and the public sign-up (#1831).

    A field of the wrong shape gets its own sentence, by the field's name; a rule
    the schema itself words (`raise ValueError("…")` in a validator) is passed on
    without the library's "Value error, " in front. None for anything else: the
    caller decides — a schema that refuses something no form can send is a fault,
    not a refusal.
    """
    from app.i18n import _

    words = {
        "date_of_birth": _("Vul een geldige geboortedatum in."),
        "relation_type": _("Kies een relatie uit de lijst."),
        "email": _("Vul een geldig e-mailadres in."),
        "extra_emails": _("Vul een geldig e-mailadres in."),
    }
    error = refusal.errors()[0]
    names = [part for part in error.get("loc", ()) if isinstance(part, str)]
    for name in reversed(names):
        if name in words:
            return words[name]
    if error.get("type") == "value_error":
        raised = (error.get("ctx") or {}).get("error")
        return str(raised) if raised is not None else None
    return None
