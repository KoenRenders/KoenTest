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
from app.domains.membership.service import (LidgegevensFout,
                                            controleer_geboortedatum_en_geslacht)
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

def family_label(family) -> str:
    """De schermnaam van een gezin (golf 9, #913): het hoofdlid, zoals de
    ledenlijst hem al toonde — die selectie stond in vijf kopieën (Jinja,
    mdm/ui 2x, payment-verrijking, audit-resolver); dit is dé bron voor de
    weergavenaam. Werkt op FamilyResponse én op alles met .members."""
    leden = getattr(family, "members", None) or []
    hoofd = next((p for p in leden
                  if getattr(p, "relation_type", None) == "HOOFDLID"),
                 leden[0] if leden else None)
    if hoofd is None:
        return f"Gezin #{family.id}"
    return f"{hoofd.last_name} {hoofd.first_name}"


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

def create_member(db: Session, data: MemberCreate, admin=None):
    """Een nieuw gezin met zijn hoofdlid.

    #713: de actor stond hier niet in de auditregel, terwijl hij bekend was — de
    functie had er zelfs een parameter voor die alleen niet gebruikt werd, en de
    JSON-route gaf hem netjes door. De snapshots schreven bovendien
    `source="system"`, dus een beheerdersactie stond genoteerd als systeemactie
    zónder actor: aan geen van beide velden te herkennen.

    `_admin` heet nu `admin`: de underscore zei "wordt niet gebruikt", en dat wás
    het probleem.
    """
    from app.domains.audit.api import snapshot_member, snapshot_member_person, snapshot_person

    wie = getattr(admin, "email", None) or (admin if isinstance(admin, str) else None)
    member = Member()
    db.add(member)
    db.flush()
    snapshot_member(db, member, operation="insert", action="member_created",
                    source="admin_manual", actor=wie)

    for person_data in data.persons:
        # #681: ook hier, want dit is de weg van het beheerscherm "Nieuw lid". Een
        # ingang die de regel overslaat maakt het gat even groot als voordien.
        try:
            controleer_geboortedatum_en_geslacht(
                person_data.date_of_birth,
                person_data.gender_code or person_data.gender)
        except LidgegevensFout as fout:
            raise HTTPException(status_code=422, detail=str(fout))

        person = Person(
            last_name=person_data.last_name,
            first_name=person_data.first_name,
            date_of_birth=person_data.date_of_birth,
            gender_code=person_data.gender_code or person_data.gender or None,
        )
        db.add(person)
        db.flush()
        snapshot_person(db, person, operation="insert", action="person_created",
                        source="admin_manual", actor=wie)

        mp = MemberPerson(
            member_id=member.id,
            person_id=person.id,
            relation_type=person_data.relation_type,
        )
        db.add(mp)
        db.flush()
        snapshot_member_person(db, mp, operation="insert", action="person_created",
                               source="admin_manual", actor=wie)

    db.commit()
    db.refresh(member)
    return member


def create_family_with_members(db: Session, data, *, actor: str, source: str,
                               membership_active: bool = False,
                               today: Optional[date] = None) -> tuple[Member, Membership]:
    """Een gezin met al zijn personen, het adres, de contactgegevens en het
    lidmaatschap — in één keer, in één transactie (#1110).

    Dit is de **ene** schrijfweg voor "maak een gezin aan". Ze stond in
    `register_router.register_family`, verweven met de publieke dedup, de betaling
    en de bevestigingsmail; de beheerkant schreef daardoor haar eigen, kortere
    versie (`create_member`: gezin + hoofdlid, meer niet) en vulde de rest met drie
    extra opslag-acties aan. Twee wegen naar hetzelfde feit, met verschillende
    regels — dat is precies de duplicatie die `CLAUDE.md` verbiedt.

    Wat per ingang verschilt, staat hier als parameter en niet als een tweede
    functie: **wie** het doet (``actor``/``source`` in de auditregels) en of het
    lidmaatschap meteen actief is (publiek niet — dat volgt op de betaling; in de
    beheerkant wél, want daar is geen betaling). Wat NIET hier hoort, blijft bij
    de publieke ingang: de dedup op het hoofdlid-e-mailadres (die gaat over een
    dubbele betaling), de betaling zelf en de bevestigingsmail.

    **Deze functie commit niet.** De publieke ingang hangt er nog een betaling aan
    vóór ze de transactie sluit; de beheerkant commit meteen. De transactiegrens
    ligt dus bij de aanroeper — en dat is precies wat "één opslaan-actie" betekent:
    faalt er iets halverwege, dan is er niets bewaard.

    De regels die hier wél staan gelden voor élke ingang: een bestaande postcode,
    en geboortedatum + geslacht voor élk lid (#681). Het adres hangt aan het
    hoofdlid (= het gezinsadres, #125).

    Geeft het gezin én zijn lidmaatschap terug: de publieke ingang hangt haar
    betaling aan dat lidmaatschap, en zonder die tweede waarde zou ze het meteen
    weer moeten opzoeken.
    """
    from app.domains.audit.api import (snapshot_address, snapshot_contact_detail,
                                       snapshot_member, snapshot_member_person,
                                       snapshot_membership, snapshot_person)
    from app.domains.payment.api import membership_valid_period

    # Eén actie voor de hele handeling: er is één gezin geregistreerd. WIE het
    # deed staat in `actor`/`source` — dat is het onderscheid, niet de naam van
    # de handeling (#1110; vóór dit issue heette de beheerweg `member_created`).
    ACTIE = "family_registered"
    vandaag = today or date.today()

    pc = db.query(PostalCode).filter(PostalCode.postal_code == data.postal_code).first()
    if not pc:
        raise HTTPException(status_code=422, detail=_("Onbekende postcode: %(postal_code)s") % {"postal_code": data.postal_code})

    # Server-side, vóór er iets geschreven wordt: de client-`required` is enkel UX.
    for lid in data.members:
        try:
            controleer_geboortedatum_en_geslacht(lid.date_of_birth,
                                                 lid.resolved_gender_code)
        except LidgegevensFout as fout:
            raise HTTPException(status_code=422, detail=str(fout))

    member = Member()
    db.add(member)
    db.flush()
    snapshot_member(db, member, operation="insert", action=ACTIE, source=source,
                    actor=actor)

    for person_data in data.members:
        person = Person(
            last_name=person_data.last_name,
            first_name=person_data.first_name,
            date_of_birth=person_data.date_of_birth,
            gender_code=person_data.resolved_gender_code,
        )
        db.add(person)
        db.flush()
        snapshot_person(db, person, operation="insert", action=ACTIE, source=source,
                        actor=actor)

        mp = MemberPerson(member_id=member.id, person_id=person.id,
                          relation_type=person_data.relation_type)
        db.add(mp)
        db.flush()
        snapshot_member_person(db, mp, operation="insert", action=ACTIE,
                               source=source, actor=actor)

        # Adres hoort enkel bij het hoofdlid (= gezinsadres). #125
        if person_data.relation_type == "HOOFDLID":
            address = Address(person_id=person.id, street=data.street,
                              house_number=data.house_number,
                              bus_number=data.bus_number or None,
                              postal_code_id=pc.id)
            db.add(address)
            db.flush()
            snapshot_address(db, address, operation="insert", action=ACTIE,
                             source=source, actor=actor)

        contacts = []
        if person_data.phone:
            contacts.append(ContactDetail(person_id=person.id, contact_type_code="PHONE",
                                          value=person_data.phone, is_primary=True))
        if person_data.mobile:
            contacts.append(ContactDetail(person_id=person.id, contact_type_code="MOBILE",
                                          value=person_data.mobile,
                                          is_primary=not person_data.phone))
        if person_data.email:
            contacts.append(ContactDetail(person_id=person.id, contact_type_code="EMAIL",
                                          value=person_data.email, is_primary=True))
        for contact in contacts:
            db.add(contact)
        if contacts:
            db.flush()
            for contact in contacts:
                snapshot_contact_detail(db, contact, operation="insert", action=ACTIE,
                                        source=source, actor=actor)

    valid_from, valid_to = membership_valid_period(vandaag)
    membership = Membership(member_id=member.id, year=vandaag.year,
                            is_active=membership_active,
                            valid_from=valid_from, valid_to=valid_to)
    db.add(membership)
    db.flush()
    snapshot_membership(db, membership, operation="insert", action=ACTIE,
                        source=source, actor=actor)
    return member, membership


def create_family_by_admin(db: Session, data, *, actor: str) -> Member:
    """De beheerweg naar een nieuw gezin: één opslaan-actie, één transactie (#1110).

    Dezelfde schrijfweg als de publieke registratie, met drie verschillen die er
    echt zijn: de beheerder tekent de auditregels (#713), er hangt geen betaling
    aan — dus het lidmaatschap is meteen actief — en er is geen dedup op het
    e-mailadres, want die bestaat om een dubbele *betaling* te voorkomen.

    De transactiegrens ligt hier en niet in het scherm: faalt er iets halverwege
    — een ongeldig tweede gezinslid, een onbekende postcode — dan blijft er niets
    half bewaard achter. Zonder dat zou het scherm een fout tonen terwijl het
    gezin en het eerste lid er wél stonden.

    Een SAVEPOINT (`begin_nested`) en geen kale `db.rollback()`: die laatste trekt
    de héle sessie terug, dus ook wat de aanroeper er vóór deze handeling in
    gezet had. Hier hoort alleen déze handeling ongedaan gemaakt te worden.
    """
    with db.begin_nested():
        member, _membership = create_family_with_members(
            db, data, actor=actor, source="admin_manual", membership_active=True)
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
        # op voornaam/achternaam/volledige naam, e-mail of STRAATNAAM van een
        # gezinslid (#233, straatnaam #1165).
        #
        # #1165: alleen de straatnaam, en de zoekterm wordt NIET opgesplitst —
        # Koen op 22 september 2026: *"Enkel straatnaam is voldoende."* Dus
        # "Kerkstraat" vindt het gezin en "Kerkstraat 12" hoeft niet te werken.
        #
        # **Zacht verwijderde adressen doen niet mee, en dat regelt de GLOBALE
        # filter** (`app/soft_delete.py`). Dat is hier het hele punt: een
        # verhuizing wist de oude adresrij niet, ze stempelt hem (vandaar de
        # PARTIËLE uniciteit op `person_id`, migratie 050), dus zonder dat filter
        # zou je een gezin terugvinden op de straat waar het vróéger woonde.
        #
        # Nagemeten op de uitgevoerde SQL i.p.v. aangenomen — want de vraag was
        # of `with_loader_criteria` ook een subquery binnen een `IN` bereikt. Dat
        # doet het: de join komt eruit als
        # `LEFT OUTER JOIN mdm.addresses ON mdm.addresses.person_id =
        # mdm.persons.id AND mdm.addresses.deleted_at IS NULL`.
        #
        # Daarom hier GEEN eigen `deleted_at`-filter: de twee joins hierboven
        # (persons, contact_details) leunen op precies dezelfde globale regel, en
        # één van de drie een eigen kopie geven doet de andere twee lezen als een
        # vergetelheid. `test_leden_zoeken_op_straat.py` bewaakt het gedrag.
        #
        # De join blijft op `person_id`: sinds #924/#945 kan een adres ook aan een
        # ORGANISATIE hangen (XOR-CHECK in de databank), en die rijen horen niet
        # in een gezinstreffer. Niet verbreden.
        like = f"%{q.strip()}%"
        match_ids = (
            db.query(MemberPerson.member_id)
            .join(Person, Person.id == MemberPerson.person_id)
            .outerjoin(ContactDetail, and_(
                ContactDetail.person_id == Person.id,
                ContactDetail.contact_type_code == "EMAIL",
            ))
            .outerjoin(Address, Address.person_id == Person.id)
            .filter(or_(
                func.concat(Person.first_name, " ", Person.last_name).ilike(like),
                Person.first_name.ilike(like),
                Person.last_name.ilike(like),
                ContactDetail.value.ilike(like),
                Address.street.ilike(like),
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
    wijzigingen = data.model_dump(exclude_unset=True)
    # #681: toets de UITKOMST, en toets ze vóór het toepassen. Een gedeeltelijke
    # wijziging (enkel de naam) mag niet afketsen op een veld dat niet meegestuurd
    # werd, maar ze mag de persoon evenmin zónder deze twee achterlaten. Vooraf,
    # niet achteraf: een `rollback()` ná het muteren gooit ook al het andere werk
    # in dezelfde sessie weg.
    try:
        controleer_geboortedatum_en_geslacht(
            wijzigingen.get("date_of_birth", person.date_of_birth),
            wijzigingen.get("gender_code", person.gender_code))
    except LidgegevensFout as fout:
        raise HTTPException(status_code=422, detail=str(fout))

    changed = False
    for field, value in wijzigingen.items():
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
        # #1111: a household created in the back office has no address row —
        # `create_member` never makes one — so "update" refused every first
        # address with 404 "Address not found", and the screen showed the
        # generic banner. Saving an address on a household without one means
        # creating it; the three required parts must all be there.
        if not (data.street and data.house_number and data.postal_code):
            raise HTTPException(
                status_code=422,
                detail=_("Straat, huisnummer en postcode zijn verplicht."))
        pc = db.query(PostalCode).filter(PostalCode.postal_code == data.postal_code).first()
        if not pc:
            raise HTTPException(status_code=422, detail=_("Onbekende postcode: %(postal_code)s") % {"postal_code": data.postal_code})
        address = Address(person_id=person.id, street=data.street,
                          house_number=data.house_number,
                          bus_number=data.bus_number or None, postal_code_id=pc.id)
        db.add(address)
        db.flush()
        snapshot_address(db, address, operation="insert", action="address_created",
                         source="admin_manual", actor=admin.email)
        db.commit()
        db.refresh(person)
        mp = next((mp for mp in person.member_persons), None)
        return _person_to_schema(person, mp.relation_type if mp else "HOOFDLID")
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

    try:
        controleer_geboortedatum_en_geslacht(data.date_of_birth, data.gender_code)
    except LidgegevensFout as fout:
        raise HTTPException(status_code=422, detail=str(fout))

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
