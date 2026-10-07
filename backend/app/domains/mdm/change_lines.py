"""How a change of member data reads: `<field>: <old> → <new>` (#1687).

The member import's check listed which fields change ("velden: telefoon,
gsm") and not what they change from and to; the changes list showed the stored
code and the stored number ("MOBILE: 0470123456"). This is the ONE presentation
of such a change, for the import's check, the applied import's result and the
contact row of the changes list:

    Mobiel: 0470 11 22 33 → 0470 44 55 66
    Telefoon: — → 014 12 34 56           (there was none)
    Mobiel: 0470 11 22 33 → (verwijderd)
    E-mail: lid@example.com               (a new person or contact: the new value only)

**The words** (Koen, 7 October 2026): a contact type and a relation read by
their label in the code table — Mobiel, E-mail, Telefoon; Hoofdlid, Partner,
(meerderjarig) kind. The fields of a person and of an address have no source
for their label yet: every screen types its own. They are typed once more
HERE, in the words of the household record — a fourth place, known and named
on the issue, until the shared source of #1692 exists. The screens still say
"Gsm" and "E-mailadres"; that difference is known too.

**The values** as the app shows them elsewhere: a phone or mobile number
through the readable formatter (#1675), a date in the Belgian form, a relation
and a gender by their label, an address on one line.

Never the import file's own column ("gsm", "telefoon", "relatie") and never
the stored code ("MOBILE") — those are how the data travels, not how it reads.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

from app.domains.mdm.codes import CONTACT
from app.i18n import _, short_date
from app.kernel.codes import code_label, code_of
from app.kernel.phone import readable_phone

EMPTY = "—"
REMOVED = "(verwijderd)"


def person_field_label(attribute: str) -> str:
    """The label of a person's field, by the model's attribute, in the words
    of the household record.

    Copy behind `_()`, not a code table: a field's name is no stored code. See
    the module's docstring: no shared source yet (#1692).
    """
    if attribute == "first_name":
        return _("Voornaam")
    if attribute == "last_name":
        return _("Achternaam")
    if attribute == "date_of_birth":
        return _("Geboortedatum")
    if attribute == "gender_code":
        return _("Geslacht")
    raise KeyError(attribute)


RELATION_LABEL = "Relatie"
ADDRESS_LABEL = "Adres"


@dataclass(frozen=True)
class FieldChange:
    """One field that changes, decided once and shown from the same pair.

    `key` is the caller's own name for the field (the report's column, a
    contact type): for counting and for tests, never for the screen. `old` is
    None when there was nothing to compare with — a new person, a new contact —
    and "" when the field existed and was empty; `new` is "" when the value goes.
    """

    key: str
    label: str
    old: Optional[str]
    new: str
    #: Set when the value itself stays and the row became the main one of its
    #: type (#1676): the one change that is no change of value.
    promoted: bool = False

    def text(self) -> str:
        if self.old is None:
            return f"{self.label}: {self.new}"
        if self.promoted and self.old == self.new:
            return f"{self.label}: {self.new} — is nu het hoofdcontact"
        return f"{self.label}: {self.old or EMPTY} → {self.new or REMOVED}"


def lines_text(changes: list[FieldChange]) -> str:
    """Several fields of one person on one line."""
    return "; ".join(change.text() for change in changes)


def contact_label(type_code: Any) -> str:
    """Mobiel, E-mail, Telefoon — the code table's own label."""
    return code_label("contact_type", code_of(type_code))


def contact_value(type_code: Any, value: Optional[str]) -> str:
    """A contact's value as it is shown: a number in groups (#1675)."""
    if not value:
        return ""
    if code_of(type_code) in (code_of(CONTACT.PHONE), code_of(CONTACT.MOBILE)):
        return readable_phone(value)
    return value


def contact_change(
    type_code: Any, old: Optional[str], new: Optional[str], **more: Any
) -> FieldChange:
    return FieldChange(
        key=str(code_of(type_code)),
        label=contact_label(type_code),
        old=None if old is None else contact_value(type_code, old),
        new=contact_value(type_code, new),
        **more,
    )


def relation_value(code: Any) -> str:
    return code_label("relation_type", code_of(code)) if code else ""


def person_value(attribute: str, value: Any) -> str:
    """A person's field as it is shown."""
    if value is None or value == "":
        return ""
    if attribute == "date_of_birth":
        return short_date(value) if isinstance(value, date) else str(value)
    if attribute == "gender_code":
        return code_label("gender", code_of(value))
    return str(value)


def person_change(key: str, attribute: str, old: Any, new: Any) -> FieldChange:
    return FieldChange(
        key=key,
        label=person_field_label(attribute),
        old=person_value(attribute, old),
        new=person_value(attribute, new),
    )


def address_line(street: Any, house_number: Any, bus_number: Any, postal_code: Any = None) -> str:
    """An address on one line: "Dorpsstraat 1 bus 2, 2400 Mol"."""
    line = f"{street or ''} {house_number or ''}".strip()
    if bus_number:
        line += f" bus {bus_number}"
    if postal_code is not None:
        place = f"{postal_code.postal_code} {postal_code.municipality}".strip()
        line = f"{line}, {place}" if line else place
    return line
