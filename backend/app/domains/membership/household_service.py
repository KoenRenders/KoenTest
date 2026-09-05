"""Gezinnen, personen en lidmaatschappen — de schrijfbewerkingen (#635 H).

Deze twaalf functies stonden als **routerfuncties** in `register_router.py`, en
`membership/api.py` gaf ze door met een lazy `__getattr__`-proxy. De facade
noemde dat "servicelaag", maar het waren HTTP-handlers met `Depends` in hun
signatuur: elk scherm dat ze gebruikte, riep in feite de JSON-router aan.

De proxy bestond om een importcyclus te vermijden — `register_router` importeert
`payment.api`, dat via `payment.service` weer `membership.api` importeert. Die
cyclus verdwijnt hier: deze module importeert geen router, en `api.py` hoeft er
geen meer te importeren.

Conventie zoals elders in de servicelaag: `db` als eerste parameter, `admin` als
optionele actor voor de history. De routes in `register_router.py` zijn dunne
schillen die deze functies aanroepen.
"""
from datetime import date
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.config import settings
from app.domains.mdm.api import (Address, ContactDetail, Member, MemberPerson,
                                 Person, PostalCode)
from app.domains.membership.models import Membership
from app.domains.membership.schemas_member import (
    AddressUpdate,
    BoardMemberAssign,
    ContactsUpdate,
    FamilyMemberResponse,
    FamilyResponse,
    MemberCreate,
    MemberResponse,
    MembershipCreate,
    MembershipResponse,
    PaginatedFamiliesResponse,
    PersonAddToFamily,
    PersonCreate,
    PersonListItem,
    PersonUpdate,
)
from app.i18n import _
from app.soft_delete import soft_delete

# De audit-snapshots worden **per functie** geïmporteerd, niet hier. `audit/api.py`
# trekt via `audit/service.py` de payment- en membership-facades binnen, en die
# importeren audit weer terug; een module-level import hier maakt de volgorde
# waarin dat oplost afhankelijk van wie er toevallig als eerste geïmporteerd wordt.
# Binnen een functie gebeurt de import pas bij de aanroep, als alles geladen is.


def _person_to_schema(person: Person, relation_type: str) -> FamilyMemberResponse:
    email = next((c.value for c in person.contact_details if c.contact_type_code == "EMAIL"), None)
    phone = next((c.value for c in person.contact_details if c.contact_type_code == "PHONE"), None)
    mobile = next((c.value for c in person.contact_details if c.contact_type_code == "MOBILE"), None)
    return FamilyMemberResponse(
        id=person.id,
        last_name=person.last_name,
        first_name=person.first_name,
        date_of_birth=person.date_of_birth,
        gender=person.gender_code,
        email=email,
        phone=phone,
        mobile=mobile,
        relation_type=relation_type,
    )

def _build_family_response(m: Member) -> FamilyResponse:
    primary = next((mp.person for mp in m.member_persons if mp.relation_type == "HOOFDLID"), None)
    address = primary.address if primary else None
    board_member = PersonListItem(
        id=m.board_member.id,
        last_name=m.board_member.last_name,
        first_name=m.board_member.first_name,
    ) if m.board_member else None
    return FamilyResponse(
        id=m.id,
        street=address.street if address else "",
        house_number=address.house_number if address else "",
        bus_number=address.bus_number if address else None,
        postal_code=address.postal_code.postal_code if address and address.postal_code else "",
        municipality=address.postal_code.municipality if address and address.postal_code else "",
        members=[_person_to_schema(mp.person, mp.relation_type) for mp in m.member_persons],
        memberships=[MembershipResponse.model_validate(ms) for ms in m.memberships],
        board_member=board_member,
    )

def _reconcile_geschrapt_lidmaatschap(
    db: Session,
    membership,
    actor: str | None,
) -> None:
    """Laat de financiële kant een geschrapt lidmaatschap volgen (#619).

    Bij activiteiten deed ``reconcile_registration_charges`` dit al; bij
    lidmaatschappen gebeurde er niets. Een onbetaalde vordering bleef dan eeuwig op de
    betalingenlijst staan voor een lidmaatschap dat niet meer bestaat, en bij een
    betaald lidmaatschap ontstond géén terugbetaling — niets signaleerde dat er geld
    terug moest. De wees-job merkt dat niet op, want die beschouwt een soft-deleted
    payable bewust als bestaand.

    ``total_due = 0``: niemand is nog iets verschuldigd, dus onbetaalde posten
    verdwijnen; een betaald bedrag blijft als financieel feit staan en levert één
    ``pending`` terugbetaling op, die de penningmeester bevestigt (zoals bij #617).
    """
    from app.domains.payment.api import reconcile_charges

    reconcile_charges(
        db, "membership", membership.id, 0, audit_actor=actor,
        source="membership-delete",
        refund_note="Automatisch bij schrappen lidmaatschap — terugstorting te bevestigen",
    )

def create_member(db: Session, data: MemberCreate, _admin=None):
    from app.domains.audit.api import snapshot_member, snapshot_member_person, snapshot_person

    member = Member()
    db.add(member)
    db.flush()
    snapshot_member(db, member, operation="insert", action="member_created", source="system")

    for person_data in data.persons:
        person = Person(
            last_name=person_data.last_name,
            first_name=person_data.first_name,
            date_of_birth=person_data.date_of_birth,
            gender_code=person_data.gender_code or person_data.gender or None,
        )
        db.add(person)
        db.flush()
        snapshot_person(db, person, operation="insert", action="person_created", source="system")

        mp = MemberPerson(
            member_id=member.id,
            person_id=person.id,
            relation_type=person_data.relation_type,
        )
        db.add(mp)
        db.flush()
        snapshot_member_person(db, mp, operation="insert", action="person_created", source="system")

    db.commit()
    db.refresh(member)
    return member

def list_families(
    db: Session,
    page: int = 1,
    page_size: int = 50,
    q: Optional[str] = None,
    status: Optional[str] = None,
    membership_year: Optional[int] = None,
    _admin=None,
):
    query = db.query(Member)
    if q and q.strip():
        # Server-side zoeken over álle leden (niet enkel de geladen pagina): match
        # op voornaam/achternaam/volledige naam of e-mail van een gezinslid (#233).
        like = f"%{q.strip()}%"
        match_ids = (
            db.query(MemberPerson.member_id)
            .join(Person, Person.id == MemberPerson.person_id)
            .outerjoin(ContactDetail, and_(
                ContactDetail.person_id == Person.id,
                ContactDetail.contact_type_code == "EMAIL",
            ))
            .filter(or_(
                func.concat(Person.first_name, " ", Person.last_name).ilike(like),
                Person.first_name.ilike(like),
                Person.last_name.ilike(like),
                ContactDetail.value.ilike(like),
            ))
            .distinct()
        )
        query = query.filter(Member.id.in_(match_ids))

    # Filters van het ledenscherm (#582). Ze werken op de query zelf, niet op de
    # opgehaalde pagina — anders zou paginering betekenisloze pagina's opleveren.
    if membership_year is not None:
        from app.domains.membership.service import members_with_membership_for_year

        query = query.filter(Member.id.in_(
            members_with_membership_for_year(db, membership_year) or {0}))
    if status in ("actief", "opgezegd"):
        from app.domains.membership.service import members_valid_on

        # Lege set → in_({0}) zodat "actief" niets teruggeeft i.p.v. alles.
        geldig = members_valid_on(db) or {0}
        query = (query.filter(Member.id.in_(geldig)) if status == "actief"
                 else query.filter(Member.id.notin_(geldig)))
    total = query.count()
    # Eager loading (#645): `_build_family_response` loopt per gezin over de
    # gezinsleden, hun persoon, adres, postcode, contactgegevens en lidmaatschappen.
    # Lui geladen waren dat vijf extra queries per gezin — bij 25 gezinnen op een
    # pagina 125 queries voor één scherm, en met htmx voel je dat rechtstreeks.
    # `selectinload` haalt elke laag in één extra query op, ongeacht het aantal
    # gezinnen.
    families = (query
                .options(
                    selectinload(Member.member_persons)
                    .selectinload(MemberPerson.person)
                    .selectinload(Person.contact_details),
                    selectinload(Member.member_persons)
                    .selectinload(MemberPerson.person)
                    .selectinload(Person.address)
                    .selectinload(Address.postal_code),
                    selectinload(Member.memberships),
                    joinedload(Member.board_member),
                )
                .order_by(Member.created_at.desc())
                .offset((page - 1) * page_size).limit(page_size).all())
    result = [_build_family_response(m) for m in families]
    return PaginatedFamiliesResponse(
        items=result,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )

def get_family(db: Session, family_id: int, _admin=None):
    m = db.query(Member).filter(Member.id == family_id).first()
    if not m:
        raise HTTPException(status_code=404, detail=_("Family not found"))
    return _build_family_response(m)

def create_membership_for_family(
    db: Session,
    family_id: int,
    data: MembershipCreate,
    admin=None,
):
    from app.domains.audit.api import snapshot_membership

    member = db.query(Member).filter(Member.id == family_id).first()
    if not member:
        raise HTTPException(status_code=404, detail=_("Family not found"))
    existing = (
        db.query(Membership)
        .filter(Membership.member_id == family_id, Membership.year == data.year)
        .first()
    )
    if existing:
        existing.is_active = data.is_active
        existing.valid_from = existing.valid_from or date(data.year, 1, 1)
        existing.valid_to = existing.valid_to or date(data.year, 12, 31)
        snapshot_membership(db, existing, operation="update", action="membership_updated", source="admin_update", actor=admin.email)
        db.commit()
        db.refresh(existing)
        return MembershipResponse.model_validate(existing)
    # Geldigheidsperiode meteen zetten, anders telt het lidmaatschap nooit als
    # 'geldig' (valid_membership_until vereist valid_from/valid_to). #143
    membership = Membership(
        member_id=family_id, year=data.year, is_active=data.is_active,
        valid_from=date(data.year, 1, 1), valid_to=date(data.year, 12, 31),
    )
    db.add(membership)
    db.flush()
    snapshot_membership(db, membership, operation="insert", action="membership_created", source="admin_manual", actor=admin.email)
    db.commit()
    db.refresh(membership)
    return MembershipResponse.model_validate(membership)

def delete_family(db: Session, family_id: int, admin=None):
    from app.domains.audit.api import snapshot_address, snapshot_contact_detail, snapshot_member, snapshot_member_person, snapshot_membership, snapshot_person

    member = db.query(Member).filter(Member.id == family_id).first()
    if not member:
        raise HTTPException(status_code=404, detail=_("Family not found"))

    # Soft delete (#166): snapshot vastleggen en deleted_at zetten — niets hard
    # verwijderen. Lidmaatschap-betalingen blijven bestaan (financieel feit); de
    # admin kan een individuele betaling apart verwijderen via het betaalscherm.
    for ms in member.memberships:
        snapshot_membership(db, ms, operation="delete", action="family_deleted", source="admin_manual", actor=admin.email)
        soft_delete(ms)
        # Stiller én groter dan één lidmaatschap schrappen, maar exact dezelfde
        # situatie (#619-3): elke betaling volgt haar eigen lidmaatschap.
        _reconcile_geschrapt_lidmaatschap(db, ms, admin.email)
    for mp in member.member_persons:
        person = mp.person
        for contact in person.contact_details:
            snapshot_contact_detail(db, contact, operation="delete", action="family_deleted", source="admin_manual", actor=admin.email)
            soft_delete(contact)
        for en in person.external_numbers:
            soft_delete(en)
        if person.address:
            snapshot_address(db, person.address, operation="delete", action="family_deleted", source="admin_manual", actor=admin.email)
            soft_delete(person.address)
        snapshot_member_person(db, mp, operation="delete", action="family_deleted", source="admin_manual", actor=admin.email)
        soft_delete(mp)
        snapshot_person(db, person, operation="delete", action="family_deleted", source="admin_manual", actor=admin.email)
        soft_delete(person)
    snapshot_member(db, member, operation="delete", action="family_deleted", source="admin_manual", actor=admin.email)
    soft_delete(member)
    db.commit()

def update_person(db: Session, person_id: int, data: PersonUpdate, admin=None):
    from app.domains.audit.api import snapshot_person

    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail=_("Person not found"))
    # Enkel snapshotten wat écht wijzigt (#188): een formulier stuurt alle velden mee,
    # maar een onveranderd veld hoort geen history-rij te maken.
    changed = False
    for field, value in data.model_dump(exclude_unset=True).items():
        if getattr(person, field) != value:
            setattr(person, field, value)
            changed = True
    if changed:
        snapshot_person(db, person, operation="update", action="person_updated", source="admin_update", actor=admin.email)
    db.commit()
    db.refresh(person)
    mp = next((mp for mp in person.member_persons), None)
    return _person_to_schema(person, mp.relation_type if mp else "HOOFDLID")

def update_person_address(
    db: Session,
    person_id: int,
    data: AddressUpdate,
    admin=None,
):
    from app.domains.audit.api import snapshot_address

    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail=_("Person not found"))
    address = person.address
    if not address:
        raise HTTPException(status_code=404, detail=_("Address not found"))
    if data.postal_code is not None:
        pc = db.query(PostalCode).filter(PostalCode.postal_code == data.postal_code).first()
        if not pc:
            raise HTTPException(status_code=422, detail=_("Onbekende postcode: %(postal_code)s") % {"postal_code": data.postal_code})
        address.postal_code_id = pc.id
    for field in ("street", "house_number"):
        value = getattr(data, field)
        if value is not None:
            setattr(address, field, value)
    if data.bus_number is not None or "bus_number" in (data.model_fields_set or set()):
        address.bus_number = data.bus_number or None
    snapshot_address(db, address, operation="update", action="address_updated", source="admin_update", actor=admin.email)
    db.commit()
    db.refresh(person)
    mp = next((mp for mp in person.member_persons), None)
    return _person_to_schema(person, mp.relation_type if mp else "HOOFDLID")

def update_person_contacts(
    db: Session,
    person_id: int,
    data: ContactsUpdate,
    admin=None,
):
    from app.domains.audit.api import snapshot_contact_detail

    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail=_("Person not found"))

    def _upsert_contact(type_code: str, value: Optional[str]):
        existing = next((c for c in person.contact_details if c.contact_type_code == type_code), None)
        if value:
            if existing:
                if existing.value != value:
                    existing.value = value
                    db.flush()
                    snapshot_contact_detail(db, existing, operation="update", action="contacts_updated", source="admin_update", actor=admin.email)
            else:
                contact = ContactDetail(person_id=person_id, contact_type_code=type_code, value=value, is_primary=True)
                person.contact_details.append(contact)
                db.flush()
                snapshot_contact_detail(db, contact, operation="insert", action="contacts_updated", source="admin_update", actor=admin.email)
        elif existing:
            snapshot_contact_detail(db, existing, operation="delete", action="contacts_updated", source="admin_update", actor=admin.email)
            person.contact_details.remove(existing)

    _upsert_contact("EMAIL", data.email)
    _upsert_contact("PHONE", data.phone)
    _upsert_contact("MOBILE", data.mobile)
    db.commit()
    db.refresh(person)
    mp = next((mp for mp in person.member_persons), None)
    return _person_to_schema(person, mp.relation_type if mp else "HOOFDLID")

def delete_person(db: Session, person_id: int, admin=None):
    from app.domains.audit.api import snapshot_address, snapshot_contact_detail, snapshot_member_person, snapshot_person

    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail=_("Person not found"))
    for contact in person.contact_details:
        snapshot_contact_detail(db, contact, operation="delete", action="person_deleted", source="admin_manual", actor=admin.email)
        soft_delete(contact)
    for en in person.external_numbers:
        soft_delete(en)
    for mp in person.member_persons:
        snapshot_member_person(db, mp, operation="delete", action="person_deleted", source="admin_manual", actor=admin.email)
        soft_delete(mp)
    if person.address:
        snapshot_address(db, person.address, operation="delete", action="person_deleted", source="admin_manual", actor=admin.email)
        soft_delete(person.address)
    snapshot_person(db, person, operation="delete", action="person_deleted", source="admin_manual", actor=admin.email)
    soft_delete(person)
    db.commit()

def add_person_to_family(
    db: Session,
    family_id: int,
    data: PersonAddToFamily,
    admin=None,
):
    from app.domains.audit.api import snapshot_contact_detail, snapshot_member_person, snapshot_person

    member = db.query(Member).filter(Member.id == family_id).first()
    if not member:
        raise HTTPException(status_code=404, detail=_("Family not found"))

    person = Person(
        last_name=data.last_name,
        first_name=data.first_name,
        date_of_birth=data.date_of_birth,
        gender_code=data.gender_code,
    )
    db.add(person)
    db.flush()
    snapshot_person(db, person, operation="insert", action="person_added_to_family", source="admin_manual", actor=admin.email)

    mp = MemberPerson(member_id=family_id, person_id=person.id, relation_type=data.relation_type)
    db.add(mp)
    db.flush()
    snapshot_member_person(db, mp, operation="insert", action="person_added_to_family", source="admin_manual", actor=admin.email)

    # Geen adres voor extra gezinsleden: het adres hoort enkel bij het hoofdlid (#125).

    for type_code, value in (("EMAIL", data.email), ("PHONE", data.phone), ("MOBILE", data.mobile)):
        if value:
            contact = ContactDetail(person_id=person.id, contact_type_code=type_code, value=value, is_primary=True)
            db.add(contact)
            db.flush()
            snapshot_contact_detail(db, contact, operation="insert", action="person_added_to_family", source="admin_manual", actor=admin.email)

    db.commit()
    db.refresh(member)
    return _build_family_response(member)

def delete_membership(db: Session, membership_id: int, admin=None):
    from app.domains.audit.api import snapshot_membership

    membership = db.query(Membership).filter(Membership.id == membership_id).first()
    if not membership:
        raise HTTPException(status_code=404, detail=_("Membership not found"))
    snapshot_membership(db, membership, operation="delete", action="membership_deleted", source="admin_manual", actor=admin.email)
    soft_delete(membership)
    _reconcile_geschrapt_lidmaatschap(db, membership, admin.email)
    db.commit()

def assign_board_member(
    db: Session,
    family_id: int,
    data: BoardMemberAssign,
    admin=None,
):
    from app.domains.audit.api import snapshot_member

    member = db.query(Member).filter(Member.id == family_id).first()
    if not member:
        raise HTTPException(status_code=404, detail=_("Family not found"))
    if data.person_id is not None:
        person = db.query(Person).filter(Person.id == data.person_id).first()
        if not person:
            raise HTTPException(status_code=404, detail=_("Person not found"))
    member.board_member_id = data.person_id
    snapshot_member(db, member, operation="update", action="board_member_assigned", source="admin_update", actor=admin.email)
    db.commit()
    db.refresh(member)
    return _build_family_response(member)
