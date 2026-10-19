"""A person who acts for an organisation (CR-26 F7, C4.7, phase 2).

An organisation that buys is registered once, by a signed-in person: *Mijn
organisatie* on the public side. The facade finds the organisation by its VAT
number within the account, or creates party, organisation, VAT identification
and address in one transaction, and makes the relation *acts for* (kind
`ACTS_FOR` of `party_relationships`) between the person and the organisation
(Koen, 15 October 2026: "Zouden we een bedrijf niet altijd verplichten een
account te maken? … Ik bedoel een persoon namens dat bedrijf." — "ja, akkoord"; no
confirmation step, Q13: "akkoord zonder bevestiging").

A second person on a VAT number already registered in the account is **linked,
not refused**, and edits nothing: the organisation's own data is the first
person's until the back office changes it. A relation is ended with an end date,
never deleted (*Ontkoppelen*), so an old order still reads who acted.

No role is stored: whoever acts for an organisation is read from the relation.
"""

from __future__ import annotations

from datetime import date
from typing import Mapping, Optional

from app.domains.mdm.organization_service import (
    _vat_number,
    _write_organization_details,
    organization_address,
    organization_details,
    update_organization_address,
)
from app.domains.mdm.tenant_service import OngeldigeInstelling
from app.i18n import _
from app.kernel.clock import belgian_today

ACTS_FOR = "ACTS_FOR"

#: What the public page writes: the organisation's own form fields, no more.
REGISTER_FIELDS = ("name", "legal_form", "vat_number", "street", "house_number", "bus_number")


def _person(db, person_id: int):
    from app.domains.mdm.models import Person

    return (
        db.query(Person)
        .filter(Person.id == person_id)
        .execution_options(include_all_tenants=True)
        .one_or_none()
    )


def organisation_by_vat(db, vat_number: str, *, account_id: int) -> Optional[int]:
    """The id of the live organisation in this account that holds this VAT number,
    or None. The number is compared as stored: `BE` and ten digits for a Belgian
    one (`_vat_number`), as typed for another country's."""
    from app.domains.mdm.models import Organization, PartyIdentification

    wanted = _vat_number(vat_number)
    row = (
        db.query(Organization.id)
        .join(PartyIdentification, PartyIdentification.party_id == Organization.party_id)
        .filter(
            Organization.account_id == account_id,
            Organization.deleted_at.is_(None),
            PartyIdentification.scheme == "VAT",
            PartyIdentification.value == wanted,
            PartyIdentification.deleted_at.is_(None),
        )
        .order_by(Organization.id)
        .execution_options(include_all_tenants=True)
        .first()
    )
    return row[0] if row else None


def register_organisation(
    db, person_id: int, form: Mapping, *, actor: Optional[str] = None
) -> tuple[int, bool]:
    """Register the organisation a person acts for; returns `(organization_id,
    created)`. One transaction: a refused form leaves nothing behind.

    The VAT number is required (Koen, 15 October 2026: "BTW-nummer zou ik
    verplicht maken bij een bestelling") and checked for its structure before the
    organisation exists. A VAT number already in the account links the person to
    that organisation (`created` is False) and writes none of the typed data."""
    from app.domains.mdm.models import Organization

    person = _person(db, person_id)
    if person is None:
        raise OngeldigeInstelling({"": _("Onbekende persoon.")})
    typed = {key: (form.get(key) or "").strip() for key in REGISTER_FIELDS}
    typed["postal_code"] = (form.get("postal_code") or "").strip()
    if not typed["vat_number"]:
        raise OngeldigeInstelling({"vat_number": _("Vul het btw-nummer van de organisatie in.")})
    typed["vat_number"] = _vat_number(typed["vat_number"])
    found = organisation_by_vat(db, typed["vat_number"], account_id=person.account_id)
    if found is not None:
        act_for(db, person_id, found)
        db.commit()
        return found, False
    if not typed["name"]:
        raise OngeldigeInstelling({"name": _("Vul de naam van de organisatie in.")})
    organisation = Organization(name=typed["name"], is_active=True, account_id=person.account_id)
    db.add(organisation)
    db.flush()
    _write_organization_details(db, organisation.id, typed, actor=actor)
    update_organization_address(db, organisation.id, typed, actor=actor)
    act_for(db, person_id, organisation.id)
    db.commit()
    return organisation.id, True


def act_for(db, person_id: int, organization_id: int, *, on_day: Optional[date] = None):
    """Make the relation *acts for* between a person and an organisation of the
    same account. Idempotent: an open relation is returned unchanged. Flushes."""
    from app.domains.mdm.models import MasterDataError, Organization, PartyRelationship

    person = _person(db, person_id)
    organisation = (
        db.query(Organization)
        .filter(Organization.id == organization_id, Organization.deleted_at.is_(None))
        .execution_options(include_all_tenants=True)
        .one_or_none()
    )
    if person is None or organisation is None or person.account_id != organisation.account_id:
        raise MasterDataError(_("Onbekende persoon of organisatie."))
    open_relation = _open_relation(db, person.party_id, organisation.party_id)
    if open_relation is not None:
        return open_relation
    relation = PartyRelationship(
        from_party_id=person.party_id,
        to_party_id=organisation.party_id,
        kind=ACTS_FOR,
        start_date=on_day or belgian_today(),
        account_id=person.account_id,
    )
    db.add(relation)
    db.flush()
    return relation


def _open_relation(db, person_party_id: int, organisation_party_id: int):
    from app.domains.mdm.models import PartyRelationship

    return (
        db.query(PartyRelationship)
        .filter(
            PartyRelationship.from_party_id == person_party_id,
            PartyRelationship.to_party_id == organisation_party_id,
            PartyRelationship.kind == ACTS_FOR,
            PartyRelationship.end_date.is_(None),
            PartyRelationship.deleted_at.is_(None),
        )
        .execution_options(include_all_tenants=True)
        .first()
    )


def end_acts_for(
    db, person_id: int, organization_id: int, *, on_day: Optional[date] = None
) -> bool:
    """*Ontkoppelen*: end the relation today (never before its start). False when
    there was none open. Flushes."""
    from app.domains.mdm.models import Organization

    person = _person(db, person_id)
    organisation = (
        db.query(Organization)
        .filter(Organization.id == organization_id)
        .execution_options(include_all_tenants=True)
        .one_or_none()
    )
    if person is None or organisation is None:
        return False
    relation = _open_relation(db, person.party_id, organisation.party_id)
    if relation is None:
        return False
    day = on_day or belgian_today()
    relation.end_date = max(day, relation.start_date) if relation.start_date else day
    db.flush()
    return True


def acts_for(db, person_id: int, organization_id: int) -> bool:
    """Does this person act for this organisation now? The one question the
    checkout and the order service ask before a *namens* order."""
    from app.domains.mdm.models import Organization

    person = _person(db, person_id)
    organisation = (
        db.query(Organization)
        .filter(Organization.id == organization_id, Organization.deleted_at.is_(None))
        .execution_options(include_all_tenants=True)
        .one_or_none()
    )
    if person is None or organisation is None:
        return False
    return _open_relation(db, person.party_id, organisation.party_id) is not None


def organisations_acting_for(db, person_id: int) -> list[dict]:
    """The organisations a person acts for now, by name: `id`, `name`, `vat_number`,
    `legal_form` — plain values, for the page and for the checkout's choice."""
    from app.domains.mdm.models import Organization, PartyRelationship

    person = _person(db, person_id)
    if person is None:
        return []
    rows = (
        db.query(Organization)
        .join(PartyRelationship, PartyRelationship.to_party_id == Organization.party_id)
        .filter(
            PartyRelationship.from_party_id == person.party_id,
            PartyRelationship.kind == ACTS_FOR,
            PartyRelationship.end_date.is_(None),
            PartyRelationship.deleted_at.is_(None),
            Organization.deleted_at.is_(None),
        )
        .order_by(Organization.name, Organization.id)
        .execution_options(include_all_tenants=True)
        .all()
    )
    out = []
    for organisation in rows:
        details = organization_details(db, organisation.id)
        out.append(
            {
                "id": organisation.id,
                "name": organisation.name,
                "vat_number": details["vat_number"],
                "legal_form": details["legal_form"],
            }
        )
    return out


def buyer_copy_of_organisation(db, organization_id: int) -> dict[str, Optional[str]]:
    """What an order copies from an organisation at placement (F8, the buyer copy):
    name, address and VAT number as they stand now. Keys are the `buyer_*` columns
    of `sales_orders` without the prefix, and `party_id` for `buyer_party_id`."""
    from app.domains.mdm.models import Address

    organisation = _organisation(db, organization_id) if organization_id else None
    if organisation is None:
        return {}
    details = organization_details(db, organization_id)
    address = organization_address(db, organization_id)
    row = (
        db.query(Address)
        .filter(Address.party_id == organisation.party_id, Address.deleted_at.is_(None))
        .order_by(Address.id)
        .execution_options(include_all_tenants=True)
        .first()
    )
    return {
        "party_id": organisation.party_id,
        "name": organisation.name,
        "street": address["street"] or None,
        "house_number": address["house_number"] or None,
        "bus_number": address["bus_number"] or None,
        "postal_code": address["postal_code"] or None,
        "municipality": (row.postal_code.municipality if row and row.postal_code else None),
        "country": "BE",
        "vat_number": details["vat_number"] or None,
    }


def _organisation(db, organization_id: int):
    from app.domains.mdm.models import Organization

    return (
        db.query(Organization)
        .filter(Organization.id == organization_id, Organization.deleted_at.is_(None))
        .execution_options(include_all_tenants=True)
        .one_or_none()
    )


def person_buyer_copy(db, person_id: int) -> dict[str, Optional[str]]:
    """The same for *voor mezelf*: the person's own party, name and address (the
    postal code and municipality of the postal code table). Empty for an unknown
    person."""
    from app.domains.mdm.models import Address

    person = _person(db, person_id)
    if person is None:
        return {}
    row = (
        db.query(Address)
        .filter(Address.party_id == person.party_id, Address.deleted_at.is_(None))
        .order_by(Address.id)
        .execution_options(include_all_tenants=True)
        .first()
    )
    postal = row.postal_code if row else None
    return {
        "party_id": person.party_id,
        "name": f"{person.first_name} {person.last_name}".strip(),
        "street": row.street if row else None,
        "house_number": row.house_number if row else None,
        "bus_number": row.bus_number if row else None,
        "postal_code": postal.postal_code if postal else None,
        "municipality": postal.municipality if postal else None,
        "country": "BE" if row else None,
        "vat_number": None,
    }


def people_of_organisation(db, organization_id: int) -> list[dict]:
    """The people linked to an organisation, for its record's card *Personen*
    (CR-26 C9): who sits in its circle or acts for it, the relation in words and its
    period. Ended relations stay in the list, with their end date — nothing was
    deleted. Plain values, newest start last."""
    from app.domains.mdm.models import PartyRelationship, Person
    from app.kernel.codes import code_label

    organisation = _organisation(db, organization_id)
    if organisation is None:
        return []
    rows = (
        db.query(PartyRelationship, Person)
        .join(Person, Person.party_id == PartyRelationship.from_party_id)
        .filter(
            PartyRelationship.to_party_id == organisation.party_id,
            PartyRelationship.deleted_at.is_(None),
            Person.deleted_at.is_(None),
        )
        .order_by(Person.first_name, Person.last_name, PartyRelationship.id)
        .execution_options(include_all_tenants=True)
        .all()
    )
    return [
        {
            "person_id": person.id,
            "name": f"{person.first_name} {person.last_name}".strip(),
            "kind": code_label("party_relationship_kind", relation.kind),
            "start_date": relation.start_date,
            "end_date": relation.end_date,
        }
        for relation, person in rows
    ]
