"""The "Word lid" form as it is sent (#1590): from field names to a `FamilyCreate`.

Word lid is one page with the household as a repeating group — the same group
and the same field names as "Mijn gezin" (`mdm.household_form`), plus what only a
sign-up carries:

    h.<key>.relation_type   the relation of a person who is not the first
    payment_method          online | transfer

The first row is the main member (hoofdlid); a later row without a relation gets
the one rule's default (`default_relation`: a partner while there is none, a
child after that).

Creating the household stays `register_family`'s; this module only reads the
form and says at which field something is missing, so a refusal can be shown
where it is and the page keeps everything that was typed. What it checks here is
the form (is this an e-mail address, is the required field filled); the rules
themselves stay on the objects and in the service, which refuse again whatever a
caller without this form sends.
"""

from __future__ import annotations

from typing import Any, Optional

from pydantic import EmailStr, TypeAdapter, ValidationError

from app.domains.mdm.api import (
    MainMemberMobileMissing,
    MemberPerson,
    PersonDetailsMissing,
    PersonRow,
    RelationType,
    household_from_form,
)
from app.domains.membership.schemas_family import FamilyCreate, FamilyMemberCreate
from app.domains.membership.service import default_relation
from app.i18n import _
from app.kernel.refusals import FieldError

#: The payment methods a visitor may choose on the public page.
PAYMENT_METHODS = ("online", "transfer")

_EMAIL = TypeAdapter(EmailStr)


def _empty(row: PersonRow) -> bool:
    """A row the visitor added and left untouched: it is not a person."""
    return not (
        row.first_name
        or row.last_name
        or row.date_of_birth
        or row.gender_code
        or row.phone
        or row.mobile
        or any(mail.value for mail in row.emails)
    )


def _person_errors(row: PersonRow) -> list[FieldError]:
    at = f"h.{row.key}"
    if not row.first_name or not row.last_name:
        missing = "first_name" if not row.first_name else "last_name"
        return [FieldError(f"{at}.{missing}", _("Voornaam en achternaam zijn verplicht."))]
    try:
        # The rule itself (#681), asked here so its refusal lands on the field.
        MemberPerson.require_details(row.date_of_birth, row.gender_code)
    except PersonDetailsMissing as refusal:
        missing = "date_of_birth" if not row.date_of_birth else "gender_code"
        return [FieldError(f"{at}.{missing}", str(refusal))]
    return []


def _addresses(row: PersonRow, errors: list[FieldError]) -> list[str]:
    """The person's e-mail addresses, the main one first; an empty row is no
    address, and what is no e-mail address is refused at its row."""
    found: list[tuple[bool, str]] = []
    for mail in row.emails:
        if not mail.value:
            continue
        try:
            _EMAIL.validate_python(mail.value)
        except ValidationError:
            errors.append(FieldError(f"e.{mail.key}.value", _("Vul een geldig e-mailadres in.")))
            continue
        found.append((mail.primary, mail.value))
    # Stable: the marked row first, the others in the order of the form.
    return [value for _main, value in sorted(found, key=lambda pair: not pair[0])]


def signup_from_form(form: Any) -> tuple[Optional[FamilyCreate], list[FieldError]]:
    """The household this form asks to create, or what stands in its way —
    everything at once, each refusal at its field."""
    household = household_from_form(form)
    errors: list[FieldError] = list(household.errors)
    refused = {error.field for error in errors}
    rows = [row for index, row in enumerate(household.persons) if index == 0 or not _empty(row)]

    members: list[FamilyMemberCreate] = []
    relations: list[str] = []
    for index, row in enumerate(rows):
        at = f"h.{row.key}"
        asked = form.get(f"{at}.relation_type")
        relation = (
            RelationType.PRIMARY_MEMBER.value
            if index == 0
            else (asked.strip() if isinstance(asked, str) and asked.strip() else "")
            or default_relation(relations)
        )
        relations.append(relation)
        if f"{at}.date_of_birth" not in refused:
            errors.extend(_person_errors(row))
        before = len(errors)
        addresses = _addresses(row, errors)
        refused_address = len(errors) > before
        if index == 0:
            # The main member is who the association writes to and calls.
            if not addresses and not refused_address:
                first_row = row.emails[0].key if row.emails else None
                errors.append(
                    FieldError(
                        f"e.{first_row}.value" if first_row else at,
                        _("E-mailadres is verplicht voor het hoofdgezinslid."),
                    )
                )
            try:
                MemberPerson.require_main_member_mobile(row.mobile)
            except MainMemberMobileMissing as refusal:
                errors.append(FieldError(f"{at}.mobile", str(refusal)))
        try:
            members.append(
                FamilyMemberCreate(
                    first_name=row.first_name,
                    last_name=row.last_name,
                    date_of_birth=row.date_of_birth,
                    gender_code=row.gender_code,
                    email=addresses[0] if addresses else None,
                    extra_emails=addresses[1:],
                    phone=row.phone or None,
                    mobile=row.mobile or None,
                    relation_type=RelationType(relation),
                )
            )
        except ValueError:
            errors.append(FieldError(f"{at}.relation_type", _("Kies een relatie uit de lijst.")))

    address = household.address
    if address is None or not address.postal_code:
        errors.append(
            FieldError("address.postal_code", _("Selecteer een geldige postcode uit de lijst."))
        )
    for name, message in (
        ("street", _("Vul de straat in.")),
        ("house_number", _("Vul het huisnummer in.")),
    ):
        if address is None or not getattr(address, name):
            errors.append(FieldError(f"address.{name}", message))

    method = form.get("payment_method")
    if method not in PAYMENT_METHODS:
        errors.append(FieldError("payment_method", _("Kies een betaalwijze.")))

    if errors or address is None:
        return None, errors
    try:
        return (
            FamilyCreate(
                street=address.street,
                house_number=address.house_number,
                bus_number=address.bus_number or None,
                postal_code=address.postal_code,
                payment_method=str(method),
                members=members,
            ),
            [],
        )
    except ValidationError as refusal:
        # Whatever the schema still refuses has no field of its own here.
        return None, [FieldError("", str(refusal.errors()[0].get("msg", _("Ongeldige invoer."))))]
