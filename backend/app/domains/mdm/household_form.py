"""The household as its portal form sends it (#1590): from field names to a `HouseholdSave`.

The page "Mijn gezin" is one form. Its repeating groups send, per row, an order
field with the row's key and the row's fields under that key:

    h_order=<key> …             h.<key>.first_name | last_name | date_of_birth
                                | gender_code | phone | mobile
                                | relation_type (a person added in the page)
    e_order.<person key>=<key>  e.<key>.value
    e_primary.<person key>      the key of the e-mail row marked as primary
    address.street | house_number | bus_number | postal_code

A key is the row's id, or anything else for a row added in the page. The rows are
read in the order of their order fields. The address is read only when the form
carries it; a form without address fields leaves the address alone.

Every person shows one empty e-mail field from the start (#1641, CR-11 Q77),
so **an empty e-mail row that was never stored is no row**: it is left out
here, once, for Word lid and Mijn gezin alike — no address is written and
nothing is refused. A STORED row that comes back empty stays: emptied means
removed. Where an address is asked (the main member of a sign-up), the refusal
still needs a field to stand on: `PersonRow.email_field` is the first e-mail
field the form sent, empty or not.

This module reads the SHAPE — a date is a date — and notes at its field what is
not (`HouseholdSave.errors`); what a value MEANS is the save's
(`mdm.household_save`), which reports everything together.
"""

from __future__ import annotations

from datetime import date
from typing import Any, Optional

from app.domains.mdm.household_save import (
    ADDRESS_FIELDS,
    AddressRow,
    EmailRow,
    HouseholdSave,
    PersonRow,
)
from app.i18n import _
from app.kernel.refusals import FieldError


def _text(form: Any, name: str) -> str:
    value = form.get(name)
    return value.strip() if isinstance(value, str) else ""


def _date(form: Any, name: str, errors: list[FieldError]) -> Optional[date]:
    raw = _text(form, name)
    if not raw:
        return None
    try:
        return date.fromisoformat(raw)
    except ValueError:
        # Until #1590 this was a `ValueError` no door caught: a 500.
        errors.append(FieldError(name, _("Ongeldige geboortedatum.")))
        return None


def household_from_form(form: Any) -> HouseholdSave:
    """The household this form carries."""
    errors: list[FieldError] = []
    persons = []
    for key in form.getlist("h_order"):
        primary = _text(form, f"e_primary.{key}")
        sent = [
            EmailRow(key=mail, value=_text(form, f"e.{mail}.value"), primary=mail == primary)
            for mail in form.getlist(f"e_order.{key}")
        ]
        persons.append(
            PersonRow(
                key=key,
                first_name=_text(form, f"h.{key}.first_name"),
                last_name=_text(form, f"h.{key}.last_name"),
                date_of_birth=_date(form, f"h.{key}.date_of_birth", errors),
                gender_code=_text(form, f"h.{key}.gender_code") or None,
                phone=_text(form, f"h.{key}.phone"),
                mobile=_text(form, f"h.{key}.mobile"),
                relation_type=_text(form, f"h.{key}.relation_type"),
                emails=[mail for mail in sent if mail.value or mail.key.isdigit()],
                email_field=f"e.{sent[0].key}.value" if sent else "",
            )
        )
    address = None
    if any(f"address.{name}" in form for name in ADDRESS_FIELDS):
        address = AddressRow(**{name: _text(form, f"address.{name}") for name in ADDRESS_FIELDS})
    return HouseholdSave(persons=persons, address=address, errors=errors)
