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
from typing import Mapping, Optional

from fastapi import HTTPException
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.domains.mdm.api import (
    CONTACT,
    Address,
    ContactDetail,
    Member,
    MemberPerson,
    Person,
    PersonDetailsMissing,
    RelationType,
    email_refusal,
)
from app.domains.membership.models import Membership
from app.domains.membership.schemas_family import FamilyCreate, FamilyMemberCreate
from app.domains.membership.schemas_member import (  # noqa: F401
    EmailAddressResponse,
    FamilyMemberResponse,
    FamilyResponse,
    MemberResponse,
    MembershipCreate,
    MembershipResponse,
    PaginatedFamiliesResponse,
    PersonListItem,
)
from app.i18n import _
from app.kernel.codes import code_of
from app.soft_delete import soft_delete

# The snapshot functions are imported **per function**, not here. That began as a
# way round an import cycle: `audit/service.py` pulled in the payment and
# membership facades, which imported audit back. Since CR-13 phase 4c (#1251)
# the snapshot functions are their owners' (`membership/history.py`, and mdm's
# through `mdm.api`) and `audit/service.py` imports no facade at module level,
# so that cycle is gone. The imports stand where they stood: moving them to the
# top was not part of that change and has not been tried.


def _person_to_schema(person: Person, relation_type) -> FamilyMemberResponse:
    # #1174: het HOOFDadres en daarnaast de volledige lijst. "De eerste rij" gaf
    # bij twee adressen een willekeurig antwoord — de relatie belooft geen
    # volgorde — dus kon dezelfde kaart bij twee bezoeken een ander adres tonen.
    #
    # Hoofdadres eerst, daarna op id: een lijst die van volgorde wisselt maakt de
    # knop "maak hoofdadres" onbetrouwbaar om aan te klikken.
    adressen = sorted(
        (c for c in person.contact_details if c.contact_type_code == CONTACT.EMAIL and c.value),
        key=lambda c: (not c.is_primary, c.id or 0),
    )
    # "The e-mail address" of a person is one that counts (#1733): the main one,
    # else the first confirmed one. Only when every address still waits for its
    # code is a waiting one shown — and the schema says so (`email_waiting`).
    counting = [c for c in adressen if c.confirmed_at is not None]
    shown = next((c for c in counting if c.is_primary), None) or next(
        iter(counting or adressen), None
    )
    email = shown.value if shown is not None else None
    phone = next(
        (c.value for c in person.contact_details if c.contact_type_code == CONTACT.PHONE), None
    )
    mobile = next(
        (c.value for c in person.contact_details if c.contact_type_code == CONTACT.MOBILE), None
    )
    return FamilyMemberResponse(
        emails=[
            EmailAddressResponse(
                id=c.id,
                value=c.value,
                is_primary=bool(c.is_primary),
                confirmed=c.confirmed_at is not None,
            )
            for c in adressen
        ],
        id=person.id,
        last_name=person.last_name,
        first_name=person.first_name,
        date_of_birth=person.date_of_birth,
        gender=person.gender_code,
        email=email,
        email_waiting=shown is not None and shown.confirmed_at is None,
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
    hoofd = next(
        (p for p in leden if getattr(p, "relation_type", None) == RelationType.PRIMARY_MEMBER),
        leden[0] if leden else None,
    )
    if hoofd is None:
        return f"Gezin #{family.id}"
    return f"{hoofd.last_name} {hoofd.first_name}"


def _build_family_response(m: Member) -> FamilyResponse:
    primary = next(
        (mp.person for mp in m.member_persons if mp.relation_type == RelationType.PRIMARY_MEMBER),
        None,
    )
    address = primary.address if primary else None
    board_member = (
        PersonListItem(
            id=m.board_member.id,
            last_name=m.board_member.last_name,
            first_name=m.board_member.first_name,
        )
        if m.board_member
        else None
    )
    return FamilyResponse(
        id=m.id,
        street=address.street if address else "",
        house_number=address.house_number if address else "",
        bus_number=address.bus_number if address else None,
        postal_code=address.postal_code.postal_code if address and address.postal_code else "",
        municipality=address.postal_code.municipality if address and address.postal_code else "",
        # #1340: the household's own order (`household_position`), the one the
        # family portal already shows — not the order the rows came back in.
        members=[
            _person_to_schema(mp.person, mp.relation_type)
            for mp in sorted(m.member_persons, key=MemberPerson.household_position)
        ],
        memberships=[MembershipResponse.model_validate(ms) for ms in m.memberships],
        board_member=board_member,
    )


def _membership_deleted(db: Session, membership, actor: str | None) -> None:
    """Say that this membership is deleted, so the money can follow (#619):
    `payment` subscribes to `MembershipDeleted` and reconciles its charges, in
    this transaction. Until CR-13 phase 4c (#1251) this function called payment
    itself. Not optional — publishing into silence would leave an open charge or
    a missing refund behind, so it refuses when nothing subscribes."""
    from app.kernel.contracts.membership import MembershipDeleted
    from app.kernel.events import has_subscribers, publish

    if not has_subscribers(MembershipDeleted):
        raise RuntimeError("nothing subscribes to MembershipDeleted; import payment.handlers")
    publish(MembershipDeleted(membership_id=membership.id, actor=actor), db)


#: CR-22 R9, Q28 and Q40: what the public Lid worden answers for an address that
#: is known already. One sentence for every such case — an account, a household
#: of an earlier try whose payment never came, a household of earlier years.
KNOWN_ADDRESS = "Dit e-mailadres is al gekend. Log je eerst aan om lid te worden."


def main_member_for_sign_up(db: Session, address: Optional[str], signed_in) -> Optional[Person]:
    """Who becomes the main member of a household that signs itself up: the
    signed-in account, or None for a new person — or `KnownAddress`.

    - Signed in as an ACCOUNT (a person without a household) whose confirmed
      address is the main member's → that person (R9, F7): no second person
      for one human.
    - Otherwise, when the main member's address already belongs to a person →
      refused (Q28). It also ends the second household a new try after a failed
      payment used to make (Q40): the first try's household holds the address,
      so he signs in — which proves the address — and pays from Mijn gezin,
      where the membership card shows the running payment or offers to start
      one.

    The message tells that the address is known. That is decided (Q28): it is
    the same kind of answer this door already gives for an existing membership.
    The board's "lid aanmaken" does not come here — it types somebody else's
    data, and master data's own rule answers there.
    """
    from app.domains.membership.models import KnownAddress

    if not address:
        return None
    if signed_in is not None and not signed_in.member_persons:
        own = {
            (c.value or "").strip().lower()
            for c in signed_in.contact_details
            if code_of(c.contact_type_code) == code_of(CONTACT.EMAIL) and c.confirmed_at is not None
        }
        if address.strip().lower() in own:
            return signed_in
    if email_refusal(db, None, address):
        raise KnownAddress(_(KNOWN_ADDRESS))
    return None


def create_family_with_members(
    db: Session,
    data,
    *,
    actor: str,
    source: str,
    membership_active: bool = False,
    today: Optional[date] = None,
    main_member: Optional[Person] = None,
) -> tuple[Member, Membership]:
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

    `main_member` (CR-22 R9, F7; #1713): the person who becomes the main member
    instead of a new one — an account that signs up while signed in. An account
    is a person already; a second person for the same human would be the
    duplicate R9 forbids. The caller decides WHO (the door knows who is signed
    in); here he gets what the form says: the name as typed, the birth date and
    the gender a member needs, his place in the household and its address. The
    contact details he already holds stay; what the form adds is added.

    Since CR-13 phase 4c (#1251) the household itself — its persons, their
    links, the address, the contact details and their history rows — is made
    by mdm, asked through the port `CreateHousehold`; the rules named above
    are mdm's and are asked there. What is written here is the membership.
    """
    from app.domains.mdm.api import HOUSEHOLD_REGISTERED, HouseholdRefused
    from app.domains.membership.history import snapshot_membership
    from app.domains.payment.api import membership_valid_period
    from app.kernel.contracts.mdm import CreateHousehold, HouseholdPerson
    from app.kernel.ports import call

    vandaag = today or date.today()
    try:
        created = call(
            CreateHousehold(
                street=data.street,
                house_number=data.house_number,
                bus_number=data.bus_number,
                postal_code=data.postal_code,
                persons=tuple(
                    HouseholdPerson(
                        first_name=given.first_name,
                        last_name=given.last_name,
                        relation_type=RelationType(given.relation_type).value,
                        date_of_birth=given.date_of_birth,
                        gender_code=given.resolved_gender_code,
                        phone=given.phone,
                        mobile=given.mobile,
                        emails=tuple(
                            str(address)
                            for address in (given.email, *given.extra_emails)
                            if address
                        ),
                    )
                    for given in data.members
                ),
                source=source,
                actor=actor,
                main_person_id=main_member.id if main_member is not None else None,
            ),
            db,
        )
    except (HouseholdRefused, PersonDetailsMissing) as refusal:
        # mdm's rules, with the status this service's doors give a refusal.
        raise HTTPException(status_code=422, detail=str(refusal)) from refusal
    member = db.get(Member, created.household_id)
    assert member is not None  # made by the port, in this transaction

    valid_from, valid_to = membership_valid_period(vandaag)
    membership = Membership(
        member_id=member.id,
        year=vandaag.year,
        is_active=membership_active,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    db.add(membership)
    db.flush()
    snapshot_membership(
        db,
        membership,
        operation="insert",
        action=HOUSEHOLD_REGISTERED,
        source=source,
        actor=actor,
    )
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
            db, data, actor=actor, source="admin_manual", membership_active=True
        )
    db.commit()
    db.refresh(member)
    return member


# De velden die `list_families` doorzoekt, met de naam die een MENS eraan geeft
# (#1165, #1167, #1169). Eén bron voor wat de grijze zoeksuggestie op /admin/leden
# belooft — #1165 gaf de `OR` een tak erbij en de tekst bleef stil achter. (Until
# CR-13 phase 4b, #1251, the description of `q` on the JSON route `GET /families`
# was derived from this list too; the route had no caller and is gone.)
#
# Nederlandse woorden in een Engelse module: dit is COPY en geen identifier, zoals
# de taalregel in `CLAUDE.md` het onderscheidt. Ze hangen hier omdat het een feit
# over déze functie is, niet over een scherm.
#
# De schermsuggestie kan hier niet uit afgeleid worden: die moet als één letterlijke string in een
# `_()`-aanroep staan, anders haalt pybabel er geen msgid meer uit. Daar staat
# dus een poort op in plaats van een afleiding — `test_leden_zoeken_op_straat.py`
# eist dat de suggestie exact deze velden noemt, en bewijst per veld dát erop
# gezocht wordt.
SEARCHED_FIELDS: tuple[str, ...] = ("naam", "straatnaam", "e-mail")


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
            .outerjoin(
                ContactDetail,
                and_(
                    ContactDetail.person_id == Person.id,
                    ContactDetail.contact_type_code == CONTACT.EMAIL,
                ),
            )
            .outerjoin(Address, Address.person_id == Person.id)
            .filter(
                or_(
                    func.concat(Person.first_name, " ", Person.last_name).ilike(like),
                    Person.first_name.ilike(like),
                    Person.last_name.ilike(like),
                    ContactDetail.value.ilike(like),
                    Address.street.ilike(like),
                )
            )
            .distinct()
        )
        query = query.filter(Member.id.in_(match_ids))

    # Filters van het ledenscherm (#582). Ze werken op de query zelf, niet op de
    # opgehaalde pagina — anders zou paginering betekenisloze pagina's opleveren.
    if membership_year is not None:
        from app.domains.membership.service import members_with_membership_for_year

        query = query.filter(
            Member.id.in_(members_with_membership_for_year(db, membership_year) or {0})
        )
    if status in ("actief", "opgezegd"):
        from app.domains.membership.service import members_valid_on

        # Lege set → in_({0}) zodat "actief" niets teruggeeft i.p.v. alles.
        geldig = members_valid_on(db) or {0}
        query = (
            query.filter(Member.id.in_(geldig))
            if status == "actief"
            else query.filter(Member.id.notin_(geldig))
        )
    total = query.count()
    # Eager loading (#645): `_build_family_response` loopt per gezin over de
    # gezinsleden, hun persoon, adres, postcode, contactgegevens en lidmaatschappen.
    # Lui geladen waren dat vijf extra queries per gezin — bij 25 gezinnen op een
    # pagina 125 queries voor één scherm, en met htmx voel je dat rechtstreeks.
    # `selectinload` haalt elke laag in één extra query op, ongeacht het aantal
    # gezinnen.
    families = (
        query.options(
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
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
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
    from app.domains.membership.history import snapshot_membership

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
        snapshot_membership(
            db,
            existing,
            operation="update",
            action="membership_updated",
            source="admin_update",
            actor=admin.email,
        )
        db.commit()
        db.refresh(existing)
        return MembershipResponse.model_validate(existing)
    # Geldigheidsperiode meteen zetten, anders telt het lidmaatschap nooit als
    # 'geldig' (valid_membership_until vereist valid_from/valid_to). #143
    membership = Membership(
        member_id=family_id,
        year=data.year,
        is_active=data.is_active,
        valid_from=date(data.year, 1, 1),
        valid_to=date(data.year, 12, 31),
    )
    db.add(membership)
    db.flush()
    snapshot_membership(
        db,
        membership,
        operation="insert",
        action="membership_created",
        source="admin_manual",
        actor=admin.email,
    )
    db.commit()
    db.refresh(membership)
    return MembershipResponse.model_validate(membership)


def delete_memberships_of_household(db: Session, household_id: int, actor: str | None) -> None:
    """A household is deleted (`HouseholdDeleted`, published by mdm): its
    memberships go with it — a soft delete (#166) with a history row each. The
    payments stay (a financial fact) and follow their own membership (#619-3):
    each deletion is said in turn, as when one membership is deleted.

    Read from membership's own table by the household's id, never through the
    household: it is soft-deleted by now. No commit — the transaction is the
    deletion's."""
    from app.domains.membership.history import snapshot_membership

    memberships = (
        db.query(Membership).filter(Membership.member_id == household_id).order_by(Membership.id)
    )
    for membership in memberships.all():
        snapshot_membership(
            db,
            membership,
            operation="delete",
            action="family_deleted",
            source="admin_manual",
            actor=actor,
        )
        soft_delete(membership)
        _membership_deleted(db, membership, actor)


def family_from_rows(values: Mapping[str, str], rows: list[dict]) -> FamilyCreate:
    """What the board's "Nieuw lid" form carries, as the household to create: the
    address fields and one member per filled-in row (`parse_member_rows`). The
    first row is the main member unless the row says otherwise, the others are
    partners.

    A household has at least its main member: no row at all is refused here, in
    the words the screen always gave. That rule stood in the screen until CR-13
    phase 4c (#1251)."""
    if not rows:
        raise HTTPException(status_code=422, detail=_("Vul minstens het hoofdlid in."))
    return FamilyCreate(
        street=(values.get("street") or "").strip(),
        house_number=(values.get("house_number") or "").strip(),
        bus_number=(values.get("bus_number") or "").strip() or None,
        postal_code=(values.get("postal_code") or "").strip(),
        members=[
            FamilyMemberCreate(
                first_name=row["first_name"],
                last_name=row["last_name"],
                date_of_birth=row["date_of_birth"] or None,
                gender_code=row["gender_code"] or None,
                email=row["email"] or None,
                phone=row["phone"] or None,
                mobile=row["mobile"] or None,
                relation_type=row["relation_type"] or ("HOOFDLID" if i == 0 else "PARTNER"),
            )
            for i, row in enumerate(rows)
        ],
    )


def delete_membership(db: Session, membership_id: int, admin=None):
    from app.domains.membership.history import snapshot_membership

    membership = db.query(Membership).filter(Membership.id == membership_id).first()
    if not membership:
        raise HTTPException(status_code=404, detail=_("Membership not found"))
    snapshot_membership(
        db,
        membership,
        operation="delete",
        action="membership_deleted",
        source="admin_manual",
        actor=admin.email,
    )
    soft_delete(membership)
    _membership_deleted(db, membership, admin.email)
    db.commit()
