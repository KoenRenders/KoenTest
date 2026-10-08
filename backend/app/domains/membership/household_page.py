"""What the three household pages show (#1590): Word lid, Mijn gezin and the renewal.

The pages share one picture of a household — its persons as a repeating group,
each with its e-mail addresses, and the address — so they share these views. A
view is what the template may ask for and nothing else: every label and every
"may this row go" is decided here, not in the template.

Keys: a stored person or e-mail row carries its id as key; a row that does not
exist yet carries a key that is not a number (`n…`), which is how the save tells
them apart (`mdm.household_save`).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Optional

from app.domains.mdm.api import CONTACT, RelationType
from app.domains.membership.membership_card import MembershipCard
from app.i18n import _

#: The tokens the page replaces by a fresh key when a row is added.
PERSON_TOKEN = "__H__"
EMAIL_TOKEN = "__E__"


@dataclass(frozen=True)
class EmailView:
    key: str
    value: str = ""
    primary: bool = False
    #: The address waits for its code (CR-22 R15, #1711): it does not sign
    #: in and receives nothing yet. The row says so and offers the code.
    pending: bool = False


@dataclass(frozen=True)
class PersonView:
    """One person of the household, as a row of the group."""

    key: str
    prefix: str
    title: str
    subtitle: str
    is_main: bool
    relation_type: str = ""
    first_name: str = ""
    last_name: str = ""
    date_of_birth: str = ""
    birth_display: str = ""
    gender_code: str = ""
    mobile: str = ""
    phone: str = ""
    emails: tuple[EmailView, ...] = ()
    #: The key of the main address, "" when there is none.
    primary_key: str = ""
    #: May this row be taken out in the page.
    removable: bool = False
    #: "open" or "closed": how the row stands when the page opens.
    fold: str = "closed"
    #: The relation is chosen on this row: a person added in the page, on Word lid
    #: and on Mijn gezin alike (#1603). Never for the main member, and not for a
    #: person who is already in the household.
    choose_relation: bool = False


@dataclass(frozen=True)
class AddressView:
    street: str = ""
    house_number: str = ""
    bus_number: str = ""
    postal_code: str = ""


@dataclass(frozen=True)
class HouseholdGroup:
    """The household as the pages show it, with what a new row is made from.

    The main member stands apart (#1632): a fixed section, first on the page.
    `members` are the others — the rows of the group Gezinsleden."""

    main: PersonView
    members: tuple[PersonView, ...]
    new_person: PersonView
    new_email: EmailView
    gender_options: tuple[tuple[str, str], ...]
    relation_options: tuple[tuple[str, str], ...]
    postal_options: tuple[tuple[str, str], ...]
    #: Always there (#1603): a household without an address shows the section
    #: with empty fields, and filling them in creates it.
    address: AddressView
    #: The address is asked: a sign-up, or a household that has one (an address
    #: is whole or it is not there). False: the section may stay empty.
    address_required: bool = True
    #: The main member's e-mail address and mobile number are asked (a sign-up;
    #: Mijn gezin asks neither, #1603).
    contact_required: bool = False


@dataclass(frozen=True)
class PersonBlock:
    """The person block for ONE person on a page of their own (Mijn gegevens,
    CR-22 S6a, #1710): what `person_fields` and `email_group` read from the
    household's group, and nothing of a household."""

    person: PersonView
    new_email: EmailView
    #: An e-mail address and a mobile number are not asked here (as on Mijn
    #: gezin, #1603).
    contact_required: bool = False


def person_block(person: Any, *, edit: bool = False) -> PersonBlock:
    """The block of this person (an `mdm` Person): the name, the mobile number
    and the e-mail rows. `edit`: without an address, one empty field to type one
    in (#1641) — a row that was never stored, which the form's reader leaves out
    when it comes back empty."""
    rows = [c for c in person.contact_details if c.deleted_at is None]
    stored = sorted(
        (c for c in rows if c.contact_type_code == CONTACT.EMAIL),
        key=lambda c: (not c.is_primary, c.id),
    )
    emails = tuple(
        EmailView(
            key=str(c.id),
            value=c.value or "",
            primary=bool(c.is_primary),
            pending=c.confirmed_at is None,
        )
        for c in stored
    )
    if edit and not emails:
        emails = (EmailView(key=f"n{person.id}e", primary=True),)
    mobile = next((c.value or "" for c in rows if c.contact_type_code == CONTACT.MOBILE), "")
    view = PersonView(
        key=str(person.id),
        prefix="",
        title=f"{person.first_name or ''} {person.last_name or ''}".strip(),
        subtitle="",
        is_main=False,
        first_name=person.first_name or "",
        last_name=person.last_name or "",
        mobile=mobile,
        emails=emails,
        primary_key=next((m.key for m in emails if m.primary), ""),
    )
    return PersonBlock(person=view, new_email=EmailView(key=EMAIL_TOKEN))


@dataclass(frozen=True)
class Terms:
    """What a membership costs and until when it runs."""

    amount: Decimal
    valid_to: date


@dataclass(frozen=True)
class SignupPage:
    group: HouseholdGroup
    terms: Terms
    #: The sign-up went through: the page reports instead of asking.
    done: bool = False
    to_checkout: bool = False


@dataclass(frozen=True)
class HouseholdPage:
    group: HouseholdGroup
    edit: bool
    #: How the membership stands: its own view-model, shown here and on the
    #: landing page (CR-22 S2, #1705).
    card: MembershipCard
    #: The page answers a save: it says "Opgeslagen ✓".
    saved: bool = False


@dataclass(frozen=True)
class RenewPage:
    valid_until: Optional[date]
    renewal_available: bool
    terms: Optional[Terms]
    #: The household in one line per person, and its address in one.
    summary: tuple[tuple[str, str, bool], ...]
    address_line: str


def _labels(choices: list) -> dict[str, str]:
    return {str(c.code): str(c.value) for c in choices}


def _relation_code(value: object) -> str:
    return value.value if isinstance(value, RelationType) else str(value or "")


def _subtitle(relation: str, has_addresses: bool) -> str:
    """What the folded row holds. A child without an e-mail address reads
    "Persoonsgegevens"; anyone who has one, and every adult, reads both."""
    if relation == RelationType.ADULT_CHILD.value and not has_addresses:
        return _("Persoonsgegevens")
    return _("Persoonsgegevens en e-mailadressen")


def _new_rows(relation_labels: dict[str, str]) -> tuple[PersonView, EmailView]:
    child = RelationType.ADULT_CHILD.value
    person = PersonView(
        key=PERSON_TOKEN,
        prefix=relation_labels.get(child, ""),
        title=_("Nieuw gezinslid"),
        subtitle=_("Persoonsgegevens en e-mailadressen"),
        is_main=False,
        relation_type=child,
        removable=True,
        fold="open",
        choose_relation=True,
        # #1641: a new person opens with one empty e-mail field, like everyone.
        # Its key hangs on the person's token, so every added person gets their own.
        emails=(EmailView(key=PERSON_TOKEN + "e", primary=True),),
        primary_key=PERSON_TOKEN + "e",
    )
    return person, EmailView(key=EMAIL_TOKEN)


def _options(codes: dict) -> tuple[tuple, tuple, tuple, dict[str, str]]:
    relation_labels = _labels(codes["relation_types"])
    main = RelationType.PRIMARY_MEMBER.value
    return (
        tuple((str(g.code), str(g.value)) for g in codes["gender_codes"]),
        tuple((code, label) for code, label in relation_labels.items() if code != main),
        tuple(
            (str(p.postal_code), f"{p.postal_code} · {p.municipality}")
            for p in codes["postal_codes"]
        ),
        relation_labels,
    )


def signup_group(codes: dict) -> HouseholdGroup:
    """An empty sign-up: the main member, open, with one e-mail row to fill in."""
    genders, relations, postal, relation_labels = _options(codes)
    main = RelationType.PRIMARY_MEMBER.value
    new_person, new_email = _new_rows(relation_labels)
    head = PersonView(
        key="n0",
        prefix=relation_labels.get(main, ""),
        title=_("Jijzelf"),
        subtitle=_("Persoonsgegevens en e-mailadressen"),
        is_main=True,
        relation_type=main,
        emails=(EmailView(key="n0e", primary=True),),
        primary_key="n0e",
        fold="open",
    )
    return HouseholdGroup(
        main=head,
        members=(),
        new_person=new_person,
        new_email=new_email,
        gender_options=genders,
        relation_options=relations,
        postal_options=postal,
        address=AddressView(),
        contact_required=True,
    )


def household_group(
    household: dict, codes: dict, *, me: int, short_date, edit: bool = False
) -> HouseholdGroup:
    """The household of a member, from the portal's own read (`household_view`).

    `me` is the person looking: nobody takes themselves out of the household, and
    the main member stays whoever looks (#1603) — the main member is no row at
    all (#1632), and one's own row has no "Verwijderen". The rows stand closed.
    A household without a flagged main member shows its first person there.

    `edit`: a person without an e-mail address shows one empty field to type
    one in (#1641, CR-11 Q77) — a row that was never stored (its key is no
    number), which the form's reader leaves out when it comes back empty.
    Reading, such a person shows no address.
    """
    genders, relations, postal, relation_labels = _options(codes)
    new_person, new_email = _new_rows(relation_labels)
    persons = []
    address: Optional[AddressView] = None
    for p in household["persons"]:
        relation = _relation_code(p.get("relation_type"))
        emails = tuple(
            EmailView(
                key=str(m["id"]),
                value=m["value"],
                primary=bool(m["is_primary"]),
                pending=not m.get("confirmed", True),
            )
            for m in p.get("emails") or []
        )
        born = p.get("date_of_birth") or ""
        subtitle = _subtitle(relation, bool(emails))
        if edit and not emails:
            emails = (EmailView(key=f"n{p['id']}e", primary=True),)
        persons.append(
            PersonView(
                key=str(p["id"]),
                prefix=relation_labels.get(relation, ""),
                title=f"{p.get('first_name') or ''} {p.get('last_name') or ''}".strip(),
                subtitle=subtitle,
                is_main=bool(p.get("is_main_member")),
                relation_type=relation,
                first_name=p.get("first_name") or "",
                last_name=p.get("last_name") or "",
                date_of_birth=born,
                birth_display=short_date(date.fromisoformat(born)) if born else "",
                gender_code=p.get("gender_code") or "",
                mobile=p.get("mobile") or "",
                phone=p.get("phone") or "",
                emails=emails,
                primary_key=next((m.key for m in emails if m.primary), ""),
                removable=p["id"] != me and not p.get("is_main_member"),
                fold="closed",
            )
        )
        a = p.get("address")
        if a and address is None:
            address = AddressView(
                street=a.get("street") or "",
                house_number=a.get("house_number") or "",
                bus_number=a.get("bus_number") or "",
                postal_code=a.get("postal_code") or "",
            )
    main = next((p for p in persons if p.is_main), persons[0])
    return HouseholdGroup(
        main=main,
        members=tuple(p for p in persons if p is not main),
        new_person=new_person,
        new_email=new_email,
        gender_options=genders,
        relation_options=relations,
        postal_options=postal,
        address=address or AddressView(),
        address_required=address is not None,
    )


def household_summary(
    household: dict, codes: dict
) -> tuple[tuple[tuple[str, str, bool], ...], str]:
    """The household in a few lines, for the renewal page: (name, relation,
    is main member) per person, and the address in one line."""
    relation_labels = _labels(codes["relation_types"])
    lines = []
    address_line = ""
    for p in household["persons"]:
        relation = _relation_code(p.get("relation_type"))
        name = f"{p.get('first_name') or ''} {p.get('last_name') or ''}".strip()
        lines.append((name, relation_labels.get(relation, ""), bool(p.get("is_main_member"))))
        a = p.get("address")
        if a and not address_line:
            street = " ".join(part for part in (a.get("street"), a.get("house_number")) if part)
            if a.get("bus_number"):
                street = _("%(street)s bus %(bus)s") % {"street": street, "bus": a["bus_number"]}
            place = " ".join(part for part in (a.get("postal_code"), a.get("municipality")) if part)
            address_line = " · ".join(part for part in (street, place) if part)
    return tuple(lines), address_line
