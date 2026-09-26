"""Merge/survivorship voor personen (§6, fase 2 #400).

Regels:
- ``merge_persons`` verwijdert NOOIT: de bron blijft bestaan met
  ``superseded_by_id`` naar de overlever. Idempotent — nogmaals mergen van een
  al gemergde bron naar dezelfde eindoverlever is een no-op.
- Ketens worden platgeslagen: wie al naar de bron wees, wordt omgelegd naar de
  nieuwe overlever, dus ``resolve()`` is altijd één stap (O(1)).
- Unmerge kan: de vorige toestand staat als snapshot in ``person_history``
  (action ``person_merged``), en ``unmerge_person`` zet de pointer(s) terug.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Iterable, NamedTuple, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.domains.mdm.models import Person, PersonHistory
from app.kernel.contracts.mdm import EntityMerged
from app.kernel.events import publish

logger = logging.getLogger(__name__)


class MergeError(ValueError):
    """Ongeldige merge (zelfde persoon, onbestaande id, bron is al overlever...)."""


def resolve(db: Session, person_id: int) -> Optional[Person]:
    """De overlevende Person voor dit id (de persoon zelf als hij niet gemerged
    is). O(1): merge_persons houdt de keten platgeslagen."""
    person = db.get(Person, person_id)
    if person is None:
        return None
    if person.superseded_by_id is None:
        return person
    survivor = db.get(Person, person.superseded_by_id)
    return survivor if survivor is not None else person


def merge_persons(db: Session, source_id: int, target_id: int,
                  actor: Optional[str] = None) -> Person:
    """Voeg ``source`` samen in ``target``; geeft de overlever terug.

    Survivorship: de target wint; de source blijft bestaan met een pointer.
    Publiceert ``EntityMerged`` (synchroon, in-transactie). Commit is aan de
    aanroeper — merge + gevolg-handlers slagen of falen samen.
    """
    if source_id == target_id:
        raise MergeError("Een persoon kan niet met zichzelf samengevoegd worden.")
    source = db.get(Person, source_id)
    target = db.get(Person, target_id)
    if source is None or target is None:
        raise MergeError("Onbekende persoon.")
    # Werk altijd op de eind-overlever van de target (target kan zelf al
    # gemerged zijn).
    while target.superseded_by_id is not None:
        target = db.get(Person, target.superseded_by_id)

    if source.superseded_by_id == target.id:
        return target  # idempotent: al gemerged naar deze overlever
    if target.superseded_by_id == source.id or target.id == source.id:
        raise MergeError("Doelpersoon is al opgeslokt door de bron.")

    # Snapshot vóór de wijziging — dit is het unmerge-anker.
    db.add(PersonHistory(
        person_id=source.id, operation="update", action="person_merged",
        source="admin_manual", actor=actor,
        last_name=source.last_name, first_name=source.first_name,
        date_of_birth=source.date_of_birth, gender_code=source.gender_code,
    ))

    # Keten platslaan: alles wat al naar de bron wees, wijst nu naar de overlever.
    (db.query(Person)
       .filter(Person.superseded_by_id == source.id)
       .update({Person.superseded_by_id: target.id}, synchronize_session=False))
    source.superseded_by_id = target.id

    db.flush()
    publish(EntityMerged(entity_type="person", source_id=source.id,
                         target_id=target.id), db)
    logger.info("MDM: persoon #%s samengevoegd in #%s (door %s)",
                source.id, target.id, actor or "system")
    return target


def unmerge_person(db: Session, source_id: int, actor: Optional[str] = None) -> Person:
    """Draai een merge terug: de bron wordt weer zelfstandig. Personen die bij
    het platslaan van een keten naar de overlever omgelegd zijn, blijven staan —
    unmerge herstelt alleen déze persoon (gericht, geen cascade-gok)."""
    source = db.get(Person, source_id)
    if source is None or source.superseded_by_id is None:
        raise MergeError("Deze persoon is niet samengevoegd.")
    db.add(PersonHistory(
        person_id=source.id, operation="update", action="person_unmerged",
        source="admin_manual", actor=actor,
        last_name=source.last_name, first_name=source.first_name,
        date_of_birth=source.date_of_birth, gender_code=source.gender_code,
    ))
    source.superseded_by_id = None
    db.flush()
    logger.info("MDM: merge van persoon #%s teruggedraaid (door %s)",
                source.id, actor or "system")
    return source


# ── Codelijsten voor formulieren (#635 I) ────────────────────────────────────

def _uniek_op_code(rijen):
    """Eén rij per code. De codetabellen zijn tenant-gescheiden, dus dezelfde code
    kan meermaals voorkomen; een keuzelijst met dubbels is verwarrend."""
    gezien, uit = set(), []
    for rij in rijen:
        if rij.code not in gezien:
            gezien.add(rij.code)
            uit.append(rij)
    return uit


def form_code_lists(db) -> dict:
    """De keuzelijsten die de inschrijf- en ledenformulieren nodig hebben."""
    from app.domains.mdm.models import GenderCode, PostalCode, RelationTypeCode

    return {
        "gender_codes": _uniek_op_code(
            db.query(GenderCode).order_by(GenderCode.code).all()),
        "relation_types": _uniek_op_code(
            db.query(RelationTypeCode).order_by(RelationTypeCode.code).all()),
        "postal_codes": db.query(PostalCode).order_by(PostalCode.postal_code).all(),
    }


def admin_code_lists(db) -> dict:
    """Geslacht en relatietype voor de beheerformulieren.

    Nederlandstalige rijen als die er zijn, anders alles: de codetabellen zijn
    per taal gevuld en een lege keuzelijst is erger dan een Engelstalige. Daarna
    ontdubbelen op code, want dezelfde code bestaat per taal.
    """
    from app.domains.mdm.models import GenderCode, RelationTypeCode

    genders = (db.query(GenderCode).filter(GenderCode.language == "nl").all()
               or db.query(GenderCode).all())
    relations = (db.query(RelationTypeCode)
                 .filter(RelationTypeCode.language == "nl").all()
                 or db.query(RelationTypeCode).all())
    return {"gender_codes": _uniek_op_code(genders),
            "relation_types": _uniek_op_code(relations)}


def list_persons(db):
    """Alle personen, op naam — voor de keuzelijst 'bestaand lid toevoegen'."""
    from app.domains.mdm.models import Person

    return db.query(Person).order_by(Person.last_name, Person.first_name).all()


# Characters that mean something to SQL's LIKE. Escaped rather than stripped: a
# search for "O'Neil %" must find that name and nothing else (#1006).
_LIKE_SPECIAAL = str.maketrans({"\\": "\\\\", "%": "\\%", "_": "\\_"})


def search_persons(db, query: str, *, members_only: bool = False,
                   exclude_ids: Iterable[int] = (), limit: int = 15) -> list:
    """Persons whose "first last" contains `query`, case-insensitively (#1006).

    One search for every caller: the meeting circle and, from CR-10 on, the
    organiser picker. It lived in the circle SCREEN, with the note that a search
    argument would be "a second contract for one caller" — with a second caller
    that note turned into two searches drifting apart.

    `members_only` limits to people in a household (a `MemberPerson` row, any
    relation), without any test on paid dues — Koen, 16 September 2026. The
    circle deliberately does NOT use it: the support worker of the department is
    not a member and must stay findable (#939).

    Sorted by last name, first name, and id as the tiebreaker (#761), so the
    same query gives the same order on every run.
    """
    from app.domains.mdm.models import MemberPerson

    naald = (query or "").strip().lower()
    if not naald:
        return []
    patroon = f"%{naald.translate(_LIKE_SPECIAAL)}%"
    vraag = db.query(Person).filter(
        func.lower(Person.first_name + " " + Person.last_name).like(patroon, escape="\\"))
    if members_only:
        vraag = vraag.filter(db.query(MemberPerson.id)
                             .filter(MemberPerson.person_id == Person.id).exists())
    uitgesloten = list(exclude_ids)
    if uitgesloten:
        vraag = vraag.filter(~Person.id.in_(uitgesloten))
    return (vraag.order_by(Person.last_name, Person.first_name, Person.id)
            .limit(limit).all())


def is_member(db, person_id: int) -> bool:
    """Is this person in a household (#1004)?

    That is what "member" means here: everyone in a `MemberPerson` row, whatever
    the relation, without a test on paid dues — Koen, 16 September 2026. Same
    definition as `search_persons(..., members_only=True)`, and the only one.
    """
    from app.domains.mdm.models import MemberPerson

    return db.query(db.query(MemberPerson.id)
                    .filter(MemberPerson.person_id == person_id).exists()).scalar()


def list_postal_codes(db):
    from app.domains.mdm.models import PostalCode

    return db.query(PostalCode).order_by(PostalCode.postal_code).all()


# ── Names, for the outbound AI guard (CR-07 §5.8) ────────────────────────────

# Tussenvoegsels: ze horen bij een naam maar wijzen niemand aan, en ze zijn
# tegelijk doodgewone Nederlandse woorden. In de naamlijst van de wachter maken ze
# elke zin verdacht — gemeten op HDEV, waar één gezin "Van den Broeck" volstond om
# elke vraag met "van" erin te blokkeren.
#
# Bewust een vaste, korte lijst en geen woordenboek: wat hier weg moet is precies
# de groep die per definitie niet discrimineert. Een achternaam die toevallig een
# gewoon woord is (Bos, Mol, De Groot) blijft staan; dat is de bekende valse
# blokkade en die kant is de veilige.
NAME_PARTICLES = {
    "van", "de", "den", "der", "des", "het", "ten", "ter", "tot", "toe",
    "op", "in", "aan", "uit", "bij", "onder", "over", "voor",
    "vande", "vanden", "vander", "vandel", "vanhet",
    "le", "la", "les", "du", "des", "da", "di", "del", "della", "dos", "das",
    "el", "al", "bin", "ibn", "abu",
    "von", "zu", "zur", "vom",
    "mac", "mc", "san", "santa", "saint",
}

def person_name_parts(db: Session) -> set[str]:
    """Every first and last name of this tenant's people, lowercased.

    The seam guard scans an outbound AI payload against this set: a name from the
    administration in a message to a language model blocks the call. Which is why
    this lives here and not there — the guard must not know how people are stored,
    and mdm must not know what a guard is.

    Parts and not full names, deliberately. "Peeters" alone is the form a question
    actually takes ("gaat het gezin Peeters stoppen?"), and matching only
    "Jan Peeters" would sail straight past it.

    Short parts are dropped: a two-letter name is a substring of ordinary Dutch and
    would block every second question. That is a real hole, and the payload view is
    the backstop for it (CR-07 §5.8, "honest limits").

    **En de tussenvoegsels gaan eruit, wat op HDEV gemeten is.** "Van den Broeck"
    leverde `van`, `den` en `broeck` op, en de eerste twee komen in vrijwel elke
    Nederlandse zin voor. Daarmee blokkeerde de wachter "Wat is de omzet van de
    activiteiten?" — niet af en toe, maar structureel, en op een manier die er voor
    de gebruiker uitziet als een kapotte assistent in plaats van als een
    beschermingsmaatregel. Een controle die alles tegenhoudt, beschermt niets: ze
    wordt uitgezet.

    Een tussenvoegsel wijst ook niemand aan. `broeck` doet dat wel en blijft dus
    staan, net als `bos` of `mol` — dat een achternaam soms een gewoon woord is, is
    de bekende valse blokkade uit §5.8 en die kant is de veilige.
    """
    rows = db.query(Person.first_name, Person.last_name).all()
    return name_parts(waarde for rij in rows for waarde in rij)


def name_parts(values) -> set[str]:
    """Scanbare delen uit willekeurige namen — de regel van hierboven, apart.

    Losgemaakt in #1135, toen de assistent óók de contactnamen van inschrijvingen
    moest scannen. Die staan in het activiteitendomein en niet op `Person`, dus ze
    komen niet uit `person_name_parts`. Ze door een eigen splitsing halen zou
    betekenen dat "hoe een naam in scanbare delen uiteenvalt" op twee plaatsen
    staat — met de tussenvoegsel-regel, de lengtedrempel en de apostrof elk twee
    keer, en dus twee keer te vergeten bij de volgende meting.

    De regel zelf is ongewijzigd; alleen de bron is nu een argument.
    """
    parts: set[str] = set()
    for value in values:
        for part in (value or "").replace("-", " ").split():
            schoon = part.lower().strip("'\u2019")
            if len(schoon) >= 3 and schoon not in NAME_PARTICLES:
                parts.add(schoon)
    return parts


# ── The meeting circle, as a relation to the organisation (CR-09, #258) ──────

BOARD_MEETING = "BOARD_MEETING"


class CirclePerson(NamedTuple):
    """One person in a circle, with the address the mail goes to."""

    relation_id: int
    person: Person
    email: Optional[str]


def _email_of(person: Person) -> Optional[str]:
    """The person's MAIN e-mail address, or None.

    `EMAIL` is the code the whole code base uses for it (auth, activities, audit
    all read it this way).

    **The primary one, not the first (#1174).** Since a member may hold several
    addresses, "the first row" is an arbitrary pick — the relationship promises no
    order — so a screen could show a different address on every load. The main
    address is the one Raak Nationaal holds, and there is exactly one of it:
    `uq_contact_details_one_primary_per_type` (migration 053) enforces at most
    one, partially, `WHERE is_primary = true AND deleted_at IS NULL`.

    The fallback to any address is deliberate: the index guarantees *at most* one
    primary, not *at least* one. A person whose main address was removed still has
    a name to show next to, and nothing should render blank over it.

    This is for SHOWING one address. Sending is a different question and has its
    own answer per kind of mail — a newsletter goes to every address
    (`email_addresses_of_members`), a confirmation to the address its form
    carried.
    """
    adressen = [c for c in getattr(person, "contact_details", []) or []
                if c.contact_type_code == "EMAIL" and c.value]
    for contact in adressen:
        if contact.is_primary:
            return contact.value
    return adressen[0].value if adressen else None


def organization_circle(db: Session, *, relation_type: str = BOARD_MEETING,
                        on_day: Optional[date] = None) -> list[CirclePerson]:
    """Who is in this organisation's circle today, alphabetically.

    A relation counts when it has started and has not ended: ending one
    end-dates it rather than deleting it, so the attendance of an old report
    keeps resolving to the person who was there.
    """
    from app.domains.mdm.models import OrganizationPerson, Person

    if on_day is None:
        on_day = date.today()
    rows = (db.query(OrganizationPerson, Person)
            .join(Person, Person.id == OrganizationPerson.person_id)
            .filter(OrganizationPerson.relation_type == relation_type,
                    or_(OrganizationPerson.start_date.is_(None),
                        OrganizationPerson.start_date <= on_day),
                    # `>` en niet `>=`: de einddatum is de dag waaróp iemand de
                    # kring verlaat, niet zijn laatste dag erin. Met `>=` bleef
                    # wie je vandaag verwijderde nog tot morgen in de lijst staan
                    # — en dan lijkt de knop stuk (gemeld door Koen, 15 sep 2026).
                    or_(OrganizationPerson.end_date.is_(None),
                        OrganizationPerson.end_date > on_day))
            .order_by(Person.first_name.asc(), Person.last_name.asc(),
                      Person.id.asc())
            .all())
    return [CirclePerson(relation_id=relation.id, person=person,
                         email=_email_of(person))
            for relation, person in rows]


def add_to_circle(db: Session, person_id: int, *, organization_id: int,
                  relation_type: str = BOARD_MEETING,
                  on_day: Optional[date] = None):
    """Put a person in the circle. Idempotent: an existing open relation is
    returned unchanged, so a double click does not create a second row."""
    from app.domains.mdm.models import OrganizationPerson

    existing = (db.query(OrganizationPerson)
                .filter(OrganizationPerson.person_id == person_id,
                        OrganizationPerson.relation_type == relation_type,
                        OrganizationPerson.end_date.is_(None))
                .first())
    if existing is not None:
        return existing
    relation = OrganizationPerson(
        person_id=person_id, organization_id=organization_id,
        relation_type=relation_type, start_date=on_day or date.today())
    db.add(relation)
    db.commit()
    return relation


def end_circle_relation(db: Session, relation_id: int,
                        on_day: Optional[date] = None) -> None:
    """Beëindig iemands plaats in de kring — einddatum, nooit verwijderd.

    De datum is de dag waaróp hij vertrekt: vanaf dat moment staat hij niet meer
    in de kring, maar een vergadering van vóór die dag toont hem gewoon nog. Zo
    blijft de aanwezigheid van oude verslagen leesbaar zonder dat er iets
    gekopieerd hoeft te worden.
    """
    from app.domains.mdm.models import OrganizationPerson

    relation = db.get(OrganizationPerson, relation_id)
    if relation is None:
        return
    relation.end_date = on_day or date.today()
    db.commit()


def new_members_between(db: Session, start: date, end: date) -> list[dict]:
    """Households that joined in the window, as the meeting names them.

    A household has no name of its own, so it is rendered as *head member –
    partner, address* (CR-09 §3.20), built from the person relations. The
    steward is included when the administration knows one; assigning one is not
    this module's job — that happens in the national administration and returns
    through the import.
    """
    from app.domains.mdm.models import (Address, Member, MemberPerson, Person,
                                        PostalCode)

    members = (db.query(Member)
               .filter(Member.created_at >= start, Member.created_at < end)
               .order_by(Member.created_at.asc(), Member.id.asc())
               .all())
    if not members:
        return []
    ids = [m.id for m in members]
    links = (db.query(MemberPerson, Person)
             .join(Person, Person.id == MemberPerson.person_id)
             .filter(MemberPerson.member_id.in_(ids))
             .all())
    by_member: dict[int, list] = {}
    for link, person in links:
        by_member.setdefault(link.member_id, []).append((link.relation_type, person))

    person_ids = [p.id for _link, p in links]
    addresses = {}
    if person_ids:
        for address, postal in (db.query(Address, PostalCode)
                                .outerjoin(PostalCode, PostalCode.id == Address.postal_code_id)
                                .filter(Address.person_id.in_(person_ids)).all()):
            addresses[address.person_id] = (address, postal)

    out = []
    for member in members:
        people = by_member.get(member.id, [])
        head = next((p for relation, p in people if relation == "HOOFDLID"), None)
        partner = next((p for relation, p in people if relation == "PARTNER"), None)
        if head is None and people:
            head = people[0][1]
        names = [f"{p.first_name} {p.last_name}".strip()
                 for p in (head, partner) if p is not None]
        address, postal = addresses.get(getattr(head, "id", None), (None, None))
        street = ""
        if address is not None:
            street = " ".join(part for part in
                              [address.street, address.house_number] if part).strip()
            if postal is not None and postal.municipality:
                street = f"{street}, {postal.municipality}".strip(", ")
        out.append({"member_id": member.id,
                    "label": " – ".join(names) or f"gezin {member.id}",
                    "address": street,
                    "steward_person_id": member.board_member_id})
    return out


def upsert_primary_contact(db: Session, person, type_code: str,
                           value: Optional[str], *, action: str, source: str,
                           is_primary: bool = True, apply: bool = True,
                           actor: Optional[str] = None) -> None:
    """Maak, werk bij of verwijder HET HOOFDCONTACT van dit type. Eén bron (#1174).

    Deze functie stond twee keer: in `mdm/import_service` voor het
    Raak-Nationaal-rapport en als binnenfunctie in
    `membership/household_service.update_person_contacts` voor het beheerscherm.
    Allebei zochten ze *"de eerste rij van dit type"*, allebei met dezelfde fout —
    en toen ik die fout in de eerste repareerde, stond ik op het punt hem in de
    tweede opnieuw te repareren. Dat is het herkenningspunt uit `CLAUDE.md`: de
    fout is niet dat er één achterliep, de fout is dat het er twee zijn.

    **Waarom "de eerste rij" fout is.** Sinds een lid meerdere e-mailadressen mag
    hebben, kan die eerste rij een EXTRA adres zijn dat wij verzameld hebben. Het
    rapport of het formulier overschreef het dan met de hoofdwaarde, of — bij een
    lege waarde — verwijderde het. Beide stil. De relatie belooft bovendien geen
    volgorde, dus welke rij "de eerste" is, ligt niet eens vast.

    Het hoofdadres is wat Raak Nationaal kent; de extra adressen zijn van ons. Een
    niet-primaire rij raakt deze functie nooit aan.

    `apply=False` is de dry-run van de import: alles uitrekenen, niets schrijven.
    `action` en `source` gaan naar de audit-snapshot, zodat een rij uit een import
    en een rij uit het beheerscherm in de geschiedenis uit elkaar te houden zijn.
    """
    from app.domains.audit.api import snapshot_contact_detail
    from app.domains.mdm.models import ContactDetail

    van_dit_type = [c for c in person.contact_details
                    if c.contact_type_code == type_code]
    hoofd = next((c for c in van_dit_type if c.is_primary), None)

    if value:
        if hoofd is None:
            # Geen hoofdcontact, maar misschien staat deze waarde al als EXTRA rij.
            # Dan die promoveren in plaats van een tweede rij met dezelfde waarde
            # te maken — anders staat hetzelfde adres twee keer bij één persoon en
            # mag iemand dat later met de hand opruimen.
            zelfde = next((c for c in van_dit_type if c.value == value), None)
            if zelfde is not None:
                if apply:
                    zelfde.is_primary = is_primary
                    db.flush()
                    snapshot_contact_detail(db, zelfde, operation="update",
                                            action=action, source=source, actor=actor)
                return
            if apply:
                # `db.add` en NIET `person.contact_details.append`. Appenden vult de
                # relatie in de sessie, en dan telt ze bij een volgende aanroep als
                # "geladen" terwijl andere relaties van diezelfde persoon dat niet
                # zijn. Gemeten: de import zag daarna `person.address` als None
                # terwijl het adres bestond, en probeerde een tweede adres in te
                # voegen — `uq_addresses_person_id`. Acht bestaande importtests
                # vielen erop om. De import deed dit altijd al met `db.add`; die
                # vorm is hier de veilige.
                nieuw = ContactDetail(person_id=person.id, contact_type_code=type_code,
                                      value=value, is_primary=is_primary)
                db.add(nieuw)
                db.flush()
                snapshot_contact_detail(db, nieuw, operation="insert",
                                        action=action, source=source, actor=actor)
            return
        if hoofd.value == value and hoofd.is_primary == is_primary:
            return
        if apply:
            hoofd.value = value
            hoofd.is_primary = is_primary
            db.flush()
            snapshot_contact_detail(db, hoofd, operation="update",
                                    action=action, source=source, actor=actor)
        return

    if hoofd is None or not apply:
        return
    snapshot_contact_detail(db, hoofd, operation="delete",
                            action=action, source=source, actor=actor)
    person.contact_details.remove(hoofd)
    db.flush()
    # Er hoort ALTIJD precies één hoofdcontact te zijn. Blijven er extra rijen van
    # dit type over, dan wijst de oudste zich aan.
    #
    # Hier botsen twee regels uit #1174, en dit is de gekozen kant: "het hoofdadres
    # is wat Raak Nationaal heeft" zou zeggen dat er nu géén is, maar dan heeft een
    # lid wél adressen op ons scherm en krijgt het toch geen post — onzichtbaar, en
    # erger dan een hoofdadres dat het nationale programma niet kent. Terugdraaien
    # is dit blok weghalen.
    #
    # Op `id` en niet op invoegvolgorde: de relatie garandeert geen volgorde, en
    # "de oudste" is de enige keuze die bij twee runs hetzelfde oplevert.
    rest = sorted((c for c in person.contact_details
                   if c.contact_type_code == type_code and not c.is_primary),
                  key=lambda c: c.id or 0)
    if rest:
        rest[0].is_primary = True
        db.flush()
        snapshot_contact_detail(db, rest[0], operation="update",
                                action=action, source=source, actor=actor)


def email_addresses_of_members(db: Session, member_ids) -> list[str]:
    """Every e-mail address of every person in these households (#984).

    The newsletter's member audience (CR-05 §3.3): not only the main member and
    not only adults — every person of the household with an address. Lower-case
    and without duplicates, so partners sharing one address get one mail. Sorted,
    so a recipient list is the same list twice.

    **Every address, not the first one (#1174).** A member may hold more than one
    e-mail address since that issue, and the newsletter goes to all of them —
    Koen, 26 September 2026: *"nieuwsbrief moet naar beiden"*. You cannot know
    which mailbox someone reads, and the extra addresses were collected precisely
    because the portal did not know them. That is the opposite of a confirmation,
    which goes to the one address its form carried.

    Until #1174 this function called ``_email_of``, which returns the FIRST row —
    so the docstring above already promised "every address" while the code sent
    one. With one address per person nobody could tell the difference.

    The de-duplication was here before and now does a second job: twelve
    addresses on PROD sit with more than one person of the same household (a
    shared mailbox), so without the set that mailbox gets the letter twice —
    independent of anyone holding a second address.
    """
    from app.domains.mdm.models import MemberPerson, Person

    ids = list(member_ids or [])
    if not ids:
        return []
    persons = (db.query(Person)
               .join(MemberPerson, MemberPerson.person_id == Person.id)
               .filter(MemberPerson.member_id.in_(ids))
               .all())
    addresses = set()
    for person in persons:
        for contact in getattr(person, "contact_details", []) or []:
            if contact.contact_type_code == "EMAIL" and (contact.value or "").strip():
                addresses.add(contact.value.strip().lower())
    return sorted(addresses)


def gezin_tabs(db, family, viewer_email: str, actief: str) -> list[dict]:
    """De tabbalk van de gezins-recordpagina (golf 9, #913) — zelfde patroon
    als activities.record_tabs: P13 in tabvorm. Overzicht · Inschrijvingen N ·
    Betalingen N (dat laatste alleen voor wie betalingen mag zien, #544).
    De Wijzigingen-tab verviel op Koens vraag (15 sep). Lokale imports:
    auth en payment importeren zelf uit mdm."""
    from app.i18n import _
    from app.domains.auth.api import may_view_payments
    from app.domains.payment.api import count_records_for_family

    tabs = [
        {"label": _("Overzicht"),
         "href": f"/admin/leden/gezin/{family.id}",
         "active": actief == "overzicht"},
        {"label": _("Inschrijvingen") + f" {family_registration_count(db, family.id)}",
         "href": f"/admin/leden/gezin/{family.id}/inschrijvingen",
         "active": actief == "inschrijvingen"},
    ]
    if may_view_payments(db, viewer_email):
        n = count_records_for_family(db, family.id)
        tabs.append({"label": _("Betalingen") + f" {n}",
                     "href": f"/admin/leden/gezin/{family.id}/betalingen",
                     "active": actief == "betalingen"})
    return tabs


def _family_registration_ids(db, family_id: int) -> list[int]:
    """De inschrijving-ids van een gezin — via dezelfde payable-verzameling
    als de Betalingen-tab (person_id + e-mail-terugval, family_payables is
    de ene bron voor "hoort deze inschrijving bij dit gezin")."""
    from app.domains.payment.api import family_payables

    return [i for t, i in family_payables(db, family_id) if t == "registration"]


def family_registration_count(db, family_id: int) -> int:
    """Het getal op de Inschrijvingen-tab: één COUNT, zonder geschrapte
    inschrijvingen — dit is een deelnamelijst, geen financieel feit."""
    from sqlalchemy import func
    from app.domains.activities.api import Registration

    ids = _family_registration_ids(db, family_id)
    if not ids:
        return 0
    return db.query(func.count(Registration.id)).filter(
        Registration.id.in_(ids)).scalar() or 0


def family_registrations(db, family_id: int, sort: str = "datum",
                         richting: str = "asc") -> list[dict]:
    """De inschrijvingen van een gezin, per activiteit gegroepeerd (feedback
    15 sep, verving de Wijzigingen-tab): recentste activiteit eerst. De
    groepen volgen het contract van `_inschrijvingen_groepen.html` — het
    gedeelde sjabloon met de activiteitstab (unificatie, zelfde dag) — en
    binnen elke groep sorteert dezelfde whitelist-helper als daar."""
    from app.domains.activities.api import (
        Registration, enrich_registration, sorteer_inschrijvingen,
    )

    ids = _family_registration_ids(db, family_id)
    if not ids:
        return []
    regs = (db.query(Registration).filter(Registration.id.in_(ids))
            .order_by(Registration.id.desc()).all())
    per_activiteit: dict = {}
    for reg in regs:
        # Defensief: een inschrijving waarvan de activiteit niet meer zichtbaar
        # is (soft-deleted) hoort de tab niet te laten crashen; ze staat dan
        # ook niet in een deelnamelijst.
        if reg.activity is None:
            continue
        per_activiteit.setdefault(reg.activity, []).append(
            enrich_registration(reg, reg.activity))

    def _laatste_datum(activity):
        datums = [(d.end_date or d.start_date) for d in activity.dates
                  if d.start_date or d.end_date]
        return max(datums) if datums else None

    groepen = [{"naam": a.name, "aantal": len(rijen),
                "regs": sorteer_inschrijvingen(rijen, sort, richting)[0],
                "titel_url": f"/admin/activiteiten/{a.id}",
                "export_href": None, "datum": _laatste_datum(a)}
               for a, rijen in per_activiteit.items()]
    groepen.sort(key=lambda g: (g["datum"] is not None, g["datum"] or date.min),
                 reverse=True)
    return groepen


def create_person_for_circle(db: Session, *, first_name: str, last_name: str,
                             email: str, organization_id: int,
                             relation_type: str = BOARD_MEETING):
    """Een persoon aanmaken die aan de organisatie hangt en aan géén gezin (#939).

    De vergaderkring bevat mensen die geen lid zijn — de afdelingsondersteuner van
    Raak nationaal is het voorbeeld waarmee de beslissing genomen is (CR-09 §3.2).
    Tot nu was zo iemand onmogelijk aan te maken: élk pad naar een nieuwe `Person`
    liep via een gezin, dus wie geen lid was, bestond niet in de administratie en
    kon dus ook niet in de kring.

    Het gezin ontbreekt hier bewust en dat is geen half werk: `Person` staat
    los van `Member` — de koppeling is een aparte tabel. Een persoon zonder gezin
    is dus een geldige rij en geen wees.
    """
    from app.domains.mdm.models import ContactDetail, Person

    first_name = (first_name or "").strip()
    last_name = (last_name or "").strip()
    email = (email or "").strip()
    if not (first_name or last_name):
        raise ValueError("naam ontbreekt")
    person = Person(first_name=first_name, last_name=last_name)
    db.add(person)
    db.flush()
    if email:
        db.add(ContactDetail(person_id=person.id, contact_type_code="EMAIL",
                             value=email, is_primary=True))
        db.flush()
    add_to_circle(db, person.id, organization_id=organization_id,
                  relation_type=relation_type)
    return person
