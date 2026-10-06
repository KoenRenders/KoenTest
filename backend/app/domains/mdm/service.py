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
from dataclasses import dataclass
from datetime import date
from typing import Iterable, NamedTuple, Optional

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.domains.mdm.codes import CONTACT
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


def merge_persons(
    db: Session, source_id: int, target_id: int, actor: Optional[str] = None
) -> Person:
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
    db.add(
        PersonHistory(
            person_id=source.id,
            operation="update",
            action="person_merged",
            source="admin_manual",
            actor=actor,
            last_name=source.last_name,
            first_name=source.first_name,
            date_of_birth=source.date_of_birth,
            gender_code=source.gender_code,
        )
    )

    # Keten platslaan: alles wat al naar de bron wees, wijst nu naar de overlever.
    # Through the objects and not a bulk UPDATE (CR-13 phase 4): every write to a
    # Person goes through the ORM, so its rules and the flush listener see it.
    for merged in db.query(Person).filter(Person.superseded_by_id == source.id):
        merged.superseded_by_id = target.id
    source.superseded_by_id = target.id

    db.flush()
    publish(EntityMerged(entity_type="person", source_id=source.id, target_id=target.id), db)
    logger.info(
        "MDM: persoon #%s samengevoegd in #%s (door %s)", source.id, target.id, actor or "system"
    )
    return target


def unmerge_person(db: Session, source_id: int, actor: Optional[str] = None) -> Person:
    """Draai een merge terug: de bron wordt weer zelfstandig. Personen die bij
    het platslaan van een keten naar de overlever omgelegd zijn, blijven staan —
    unmerge herstelt alleen déze persoon (gericht, geen cascade-gok)."""
    source = db.get(Person, source_id)
    if source is None or source.superseded_by_id is None:
        raise MergeError("Deze persoon is niet samengevoegd.")
    db.add(
        PersonHistory(
            person_id=source.id,
            operation="update",
            action="person_unmerged",
            source="admin_manual",
            actor=actor,
            last_name=source.last_name,
            first_name=source.first_name,
            date_of_birth=source.date_of_birth,
            gender_code=source.gender_code,
        )
    )
    source.superseded_by_id = None
    db.flush()
    logger.info("MDM: merge van persoon #%s teruggedraaid (door %s)", source.id, actor or "system")
    return source


# ── Codelijsten voor formulieren (#635 I) ────────────────────────────────────


#: What a dropdown needs: the code and the word next to it. Since CR-12
#: phase 2 that comes from `code_labels()`, so from the label table and in
#: `sort_order`. A template that shows this list reads `.code` and `.value`,
#: as it did from the old rows — hence this small thing instead of a tuple:
#: the screens did not have to change along.
class _Choice:
    __slots__ = ("code", "value")

    def __init__(self, code: str, value: str):
        self.code = code
        self.value = value


def _choices(list_name: str) -> list:
    from app.kernel.codes import code_labels

    return [_Choice(code, label) for code, label in code_labels(list_name)]


def form_code_lists(db) -> dict:
    """De keuzelijsten die de inschrijf- en ledenformulieren nodig hebben."""
    from app.domains.mdm.models import PostalCode

    return {
        "gender_codes": _choices("gender"),
        "relation_types": _choices("relation_type"),
        "postal_codes": db.query(PostalCode).order_by(PostalCode.postal_code).all(),
    }


def admin_code_lists(db) -> dict:
    """Geslacht en relatietype voor de beheerformulieren.

    CR-12 phase 2: this used to say "Dutch rows if there are any, otherwise
    everything", plus a deduplication on code — both because the old code
    table had one row per (code, language) and so the code occurred several
    times. With the split shape that problem no longer exists: `code_labels()`
    returns one row per active code, in the unit's language and in
    `sort_order`.
    """
    return {"gender_codes": _choices("gender"), "relation_types": _choices("relation_type")}


def list_persons(db):
    """Alle personen, op naam — voor de keuzelijst 'bestaand lid toevoegen'."""
    from app.domains.mdm.models import Person

    return db.query(Person).order_by(Person.last_name, Person.first_name).all()


# Characters that mean something to SQL's LIKE. Escaped rather than stripped: a
# search for "O'Neil %" must find that name and nothing else (#1006).
_LIKE_SPECIAAL = str.maketrans({"\\": "\\\\", "%": "\\%", "_": "\\_"})


@dataclass(frozen=True)
class PersonMatch:
    """One search result: the person, and the address the mails would go to (#1353).

    The address is `_email_of`, the same one the meeting circle mails, or None. Two
    namesakes are told apart by it before one is added, and someone without an
    address is visible before they are added and then receive nothing. The name
    and id read through, so a caller that only lists names needs no change.
    """

    person: Person
    email: Optional[str]

    @property
    def id(self) -> int:
        return self.person.id

    @property
    def first_name(self) -> str:
        return self.person.first_name

    @property
    def last_name(self) -> str:
        return self.person.last_name


def search_persons(
    db, query: str, *, members_only: bool = False, exclude_ids: Iterable[int] = (), limit: int = 15
) -> list[PersonMatch]:
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
        func.lower(Person.first_name + " " + Person.last_name).like(patroon, escape="\\")
    )
    if members_only:
        vraag = vraag.filter(
            db.query(MemberPerson.id).filter(MemberPerson.person_id == Person.id).exists()
        )
    uitgesloten = list(exclude_ids)
    if uitgesloten:
        vraag = vraag.filter(~Person.id.in_(uitgesloten))
    return [
        PersonMatch(person=person, email=_email_of(person))
        for person in vraag.order_by(Person.last_name, Person.first_name, Person.id)
        .limit(limit)
        .all()
    ]


def household_ids(db, person_ids) -> dict[int, int]:
    """{person id: the id of a household that person belongs to} (#1559).

    A person has no page of their own; their name links to the household's. Someone
    in two households gets the one with the lowest id; someone in none is absent.
    """
    from app.domains.mdm.models import MemberPerson

    ids = list(person_ids)
    if not ids:
        return {}
    rows = (
        db.query(MemberPerson.person_id, MemberPerson.member_id)
        .filter(MemberPerson.person_id.in_(ids))
        .order_by(MemberPerson.member_id.desc())
        .all()
    )
    return {person_id: member_id for person_id, member_id in rows}


def is_member(db, person_id: int) -> bool:
    """Is this person in a household (#1004)?

    That is what "member" means here: everyone in a `MemberPerson` row, whatever
    the relation, without a test on paid dues — Koen, 16 September 2026. Same
    definition as `search_persons(..., members_only=True)`, and the only one.
    """
    from app.domains.mdm.models import MemberPerson

    return db.query(
        db.query(MemberPerson.id).filter(MemberPerson.person_id == person_id).exists()
    ).scalar()


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
    "van",
    "de",
    "den",
    "der",
    "des",
    "het",
    "ten",
    "ter",
    "tot",
    "toe",
    "op",
    "in",
    "aan",
    "uit",
    "bij",
    "onder",
    "over",
    "voor",
    "vande",
    "vanden",
    "vander",
    "vandel",
    "vanhet",
    "le",
    "la",
    "les",
    "du",
    "des",
    "da",
    "di",
    "del",
    "della",
    "dos",
    "das",
    "el",
    "al",
    "bin",
    "ibn",
    "abu",
    "von",
    "zu",
    "zur",
    "vom",
    "mac",
    "mc",
    "san",
    "santa",
    "saint",
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


#: The words of the calendar and of counting are no name parts either (#1667).
#: Measured on HDEV, 6 October 2026: someone's name there holds "derde", so
#: "de derde laatste vrijdag van december" reached the model as "de [naam]
#: laatste vrijdag" — it proposed the last Friday, and the correction after it
#: lost the same word. Like a particle, such a word points at nobody; unlike a
#: surname that happens to be a word (Bos, Mol), no request about an activity,
#: a meeting or a payment can do without them. A person who is really called
#: Mei or Zondag is no longer removed by these words alone: the same honest
#: limit as the particles, and the payload view is the backstop for it.
NAME_ORDINARY_WORDS = frozenset(
    "eerste tweede derde vierde vijfde zesde zevende achtste negende tiende elfde twaalfde "
    "laatste voorlaatste "
    "maandag dinsdag woensdag donderdag vrijdag zaterdag zondag "
    "januari februari maart april mei juni juli augustus september oktober november december".split()
)


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
            if (
                len(schoon) >= 3
                and schoon not in NAME_PARTICLES
                and schoon not in NAME_ORDINARY_WORDS
            ):
                parts.add(schoon)
    return parts


# ── The meeting circle, as a relation to the organisation (CR-09, #258) ──────

BOARD_MEETING = "BOARD_MEETING"


class CirclePerson(NamedTuple):
    """One person in a circle, with the address the mail goes to."""

    relation_id: int
    person: Person
    email: Optional[str]
    # Since when this person counts for a meeting (#1346): the circle screen shows
    # it and lets the secretary change it.
    start_date: Optional[date] = None


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
    # The choice itself is the person's since CR-13 phase 3: `primary_contact`.
    contact = person.primary_contact(CONTACT.EMAIL)
    return contact.value if contact is not None else None


def organization_circle(
    db: Session, *, relation_type: str = BOARD_MEETING, on_day: Optional[date] = None
) -> list[CirclePerson]:
    """Who is in this organisation's circle today, alphabetically.

    A relation counts when it has started and has not ended: ending one
    end-dates it rather than deleting it, so the attendance of an old report
    keeps resolving to the person who was there.
    """
    from app.domains.mdm.models import OrganizationPerson, Person

    if on_day is None:
        on_day = date.today()
    rows = (
        db.query(OrganizationPerson, Person)
        .join(Person, Person.id == OrganizationPerson.person_id)
        .filter(
            OrganizationPerson.relation_type == relation_type,
            or_(OrganizationPerson.start_date.is_(None), OrganizationPerson.start_date <= on_day),
            # `>` en niet `>=`: de einddatum is de dag waaróp iemand de
            # kring verlaat, niet zijn laatste dag erin. Met `>=` bleef
            # wie je vandaag verwijderde nog tot morgen in de lijst staan
            # — en dan lijkt de knop stuk (gemeld door Koen, 15 sep 2026).
            or_(OrganizationPerson.end_date.is_(None), OrganizationPerson.end_date > on_day),
        )
        .order_by(Person.first_name.asc(), Person.last_name.asc(), Person.id.asc())
        .all()
    )
    return [
        CirclePerson(
            relation_id=relation.id,
            person=person,
            email=_email_of(person),
            start_date=relation.start_date,
        )
        for relation, person in rows
    ]


def add_to_circle(
    db: Session,
    person_id: int,
    *,
    organization_id: int,
    relation_type: str = BOARD_MEETING,
    on_day: Optional[date] = None,
):
    """Put a person in the circle. Idempotent: an existing open relation is
    returned unchanged, so a double click does not create a second row."""
    from app.domains.mdm.models import OrganizationPerson

    existing = (
        db.query(OrganizationPerson)
        .filter(
            OrganizationPerson.person_id == person_id,
            OrganizationPerson.relation_type == relation_type,
            OrganizationPerson.end_date.is_(None),
        )
        .first()
    )
    if existing is not None:
        return existing
    relation = OrganizationPerson(
        person_id=person_id,
        organization_id=organization_id,
        relation_type=relation_type,
        start_date=on_day or date.today(),
    )
    db.add(relation)
    db.commit()
    return relation


def set_circle_start(db: Session, relation_id: int, start_date: date) -> None:
    """Change since when someone counts for the circle (#1346).

    A meeting uses the circle as it stood on its own date, and until #1346 a
    relation always started on the day it was added. Someone added today did
    not count for a meeting last month: its attendance list was empty and its
    report went to nobody. The secretary sets the real date here.

    `OrganizationPerson.check()` refuses a start after the end, on the flush.
    Reached through the `CircleStartChosen` event (`mdm.handlers`), so it never
    commits: the publisher's door does.
    """
    from app.domains.mdm.models import MasterDataError, OrganizationPerson

    relation = db.get(OrganizationPerson, relation_id)
    if relation is None:
        from app.i18n import _

        raise MasterDataError(_("Die persoon staat niet (meer) in de kring."))
    relation.start_date = start_date
    try:
        db.flush()
    except MasterDataError:
        # The check refuses before any SQL is sent; forget the refused value so
        # the screen that answers reads the row as it is.
        db.expire(relation)
        raise


def end_circle_relation(db: Session, relation_id: int, on_day: Optional[date] = None) -> None:
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
    end = on_day or date.today()
    # #1346: a start can lie in the future now. Taking such a person out ends the
    # relation on its start: it never counted, and the end may not precede it.
    if relation.start_date is not None and relation.start_date > end:
        end = relation.start_date
    relation.end_date = end
    db.commit()


def households_as_named(db: Session, member_ids: list[int]) -> list[dict]:
    """These households as the meeting names them, in the order given (#1358).

    A household has no name of its own, so it is rendered as *head member –
    partner, address* (CR-09 §3.20), built from the person relations. The
    steward is included when the administration knows one; assigning one is not
    this module's job — that happens in the national administration and returns
    through the import.

    WHICH households are new is not master data: it is the start of their first
    membership, and that rule lives in `membership` (`new_members_between`),
    which asks this function for the names. Until #1358 this function chose them
    itself, by the creation date of the record — so a catch-up import of last
    year's members showed up as new.
    """
    from app.domains.mdm.models import Address, Member, MemberPerson, Person, PostalCode

    if not member_ids:
        return []
    by_id = {m.id: m for m in db.query(Member).filter(Member.id.in_(member_ids)).all()}
    members = [by_id[i] for i in member_ids if i in by_id]
    if not members:
        return []
    ids = [m.id for m in members]
    links = (
        db.query(MemberPerson, Person)
        .join(Person, Person.id == MemberPerson.person_id)
        .filter(MemberPerson.member_id.in_(ids))
        .all()
    )
    by_member: dict[int, list] = {}
    for link, person in links:
        by_member.setdefault(link.member_id, []).append((link.relation_type, person))

    person_ids = [p.id for _link, p in links]
    addresses = {}
    if person_ids:
        for address, postal in (
            db.query(Address, PostalCode)
            .outerjoin(PostalCode, PostalCode.id == Address.postal_code_id)
            .filter(Address.person_id.in_(person_ids))
            .all()
        ):
            addresses[address.person_id] = (address, postal)

    out = []
    for member in members:
        people = by_member.get(member.id, [])
        head = next((p for relation, p in people if relation == "HOOFDLID"), None)
        partner = next((p for relation, p in people if relation == "PARTNER"), None)
        if head is None and people:
            head = people[0][1]
        names = [f"{p.first_name} {p.last_name}".strip() for p in (head, partner) if p is not None]
        address, postal = addresses.get(getattr(head, "id", None), (None, None))
        street = ""
        if address is not None:
            street = " ".join(
                part for part in [address.street, address.house_number] if part
            ).strip()
            if postal is not None and postal.municipality:
                street = f"{street}, {postal.municipality}".strip(", ")
        out.append(
            {
                "member_id": member.id,
                "label": " – ".join(names) or f"gezin {member.id}",
                "address": street,
                "steward_person_id": member.board_member_id,
            }
        )
    return out


def _persoon_of_404(db: Session, person_id: int):
    from app.domains.mdm.models import Person

    person = db.query(Person).filter(Person.id == person_id).one_or_none()
    if person is None:
        from fastapi import HTTPException

        from app.i18n import _

        raise HTTPException(status_code=404, detail=_("Persoon niet gevonden"))
    return person


def add_email_address(db: Session, person_id: int, value: str, *, actor: Optional[str] = None):
    """Zet er een e-mailadres bij (#1174). Het eerste adres wordt het hoofdadres.

    De nieuwsbriefverantwoordelijke heeft een tiental adressen die het portaal
    niet kent; dit is de weg om ze binnen te krijgen. Ze tellen mee bij het
    aanmelden en bij de nieuwsbrief, maar niet als hoofdadres — dat blijft wat
    Raak Nationaal in zijn programma heeft.

    Dezelfde waarde twee keer bij één persoon is een vergissing en geen tweede
    geval, dus die wordt stil overgeslagen in plaats van een dubbele rij te maken.
    Hoofdletterongevoelig vergeleken: een mens typt zijn eigen adres niet twee
    keer identiek.
    """
    from app.domains.audit.api import snapshot_contact_detail
    from app.domains.mdm.models import ContactDetail

    person = _persoon_of_404(db, person_id)
    waarde = (value or "").strip()
    if not waarde:
        return person
    bestaand = [c for c in person.contact_details if c.contact_type_code == CONTACT.EMAIL]
    if any((c.value or "").strip().lower() == waarde.lower() for c in bestaand):
        return person

    # Dezelfde regel als de formulierrijen (#1219): het eerste adres dat een mens
    # invoert wordt het hoofdadres, tenzij er al een is. Niet "de eerste rij" maar
    # "er is er nog geen" — de markering is een herkomst en geen positie.
    wordt_hoofd = not _heeft_hoofdadres(person)
    rij = ContactDetail(
        person_id=person.id, contact_type_code="EMAIL", value=waarde, is_primary=wordt_hoofd
    )
    db.add(rij)
    db.flush()
    snapshot_contact_detail(
        db,
        rij,
        operation="insert",
        action="email_promoted" if wordt_hoofd else "email_added",
        source="admin_update",
        actor=actor,
    )
    db.commit()
    db.refresh(person)
    return person


def _heeft_hoofdadres(person) -> bool:
    """Draagt deze persoon al een hoofd-e-mailadres? (#1219)

    Eén plek, want twee invoerwegen stellen dezelfde vraag: de rijen in het
    ledenformulier en de losse toevoegknop van de JSON-API.
    """
    return any(c.is_primary for c in person.contact_details if c.contact_type_code == CONTACT.EMAIL)


def apply_email_rows(
    db: Session, person_id: int, formulier, *, actor: Optional[str] = None
) -> None:
    """Pas de e-mailadres-RIJEN uit een ledenformulier toe (#1219).

    Tot dit issue waren de adressen drie losse acties: toevoegen, hoofdadres
    maken, verwijderen. Koen vroeg hoe je dan een tikfout in een niet-hoofdadres
    corrigeert, en het antwoord was *"weggooien en opnieuw toevoegen"* — want er
    was geen veld om in te typen. Nu zijn het rijen in het formulier, en het
    opslaan van het lid slaat ook de tekst op. Zelfde vorm als de gezinsleden op
    *Word lid* en het aanmaakscherm (#1110): één formulier, één opslaan, één
    transactie.

    Verwijderen en hoofdadres aanduiden blijven eigen knoppen — dat zijn losse
    beslissingen met een eigen betekenis in het auditspoor, geen tekst.

    Twee soorten veld:

    - ``email_existing_<id>`` — een rij die al bestaat. Wijzigt de tekst, dan
      volgt de waarde. **Leeg betekent weg**: dat is wat een formulier nu eenmaal
      zegt, en de knop ernaast blijft de snelle weg. Beide worden geauditeerd.
    - ``email_new_<n>`` — een rij die de bezoeker zojuist toevoegde. Die heeft nog
      geen id; een lege laat je gewoon vallen.

    **Het eerste adres dat een MENS invoert wordt wél het hoofdadres**, en dat is
    geen tegenspraak met #1174. Koen, 26 september 2026: *"Als je maar 1 adres
    invoert is dat het hoofdadres."* Wie het intypt zegt iets — dít is het adres —
    en er is niets anders dat het kan zijn. De IMPORT promoveert daarentegen nooit:
    draagt het rapport geen adres meer, dan blijft er geen hoofdadres over, want
    daar zou promoveren iets bewéren over wat Raak Nationaal heeft. Twee
    herkomsten, twee regels.

    Bestaat er al een hoofdadres, dan krijgt een nieuwe rij het niet. En de
    markering volgt de VOLGORDE niet: staat ze op de tweede rij, dan blijft ze daar
    na opslaan en herladen. "Het eerste adres" gaat over invoeren, niet over
    weergeven.
    """
    person = _persoon_of_404(db, person_id)

    def _waarde(sleutel: str) -> str:
        ruw = formulier.get(sleutel)
        return ruw.strip() if isinstance(ruw, str) else ""

    existing: dict[int, str] = {}
    new: list[str] = []
    for sleutel in list(formulier.keys()):
        if sleutel.startswith("email_existing_"):
            try:
                existing[int(sleutel.removeprefix("email_existing_"))] = _waarde(sleutel)
            except ValueError:
                continue
        elif sleutel.startswith("email_new_"):
            new.append(_waarde(sleutel))

    if write_email_rows(db, person, existing, new, actor=actor):
        # **Commit, geen flush** (#1223). De aanroeper heeft zijn eigen wijziging
        # al vastgelegd vóór deze functie draait, dus na een flush alleen wordt
        # dit weer weggegooid bij het einde van het verzoek: de rij verschijnt, de
        # POST vertrekt, de server antwoordt 200 — en er staat niets in de
        # databank.
        #
        # Mijn pytests zagen dat niet: die lezen door DEZELFDE sessie, en daarin
        # is een geflushte rij gewoon zichtbaar. Alleen een tweede verbinding —
        # de browser — kent het verschil. Dat is dezelfde vorm als de test die
        # het onderwerp omzeilt, één laag dieper.
        db.commit()


def write_email_rows(
    db: Session,
    person,
    existing: dict[int, str],
    new: list[str],
    *,
    actor: Optional[str] = None,
    source: str = "admin_update",
) -> bool:
    """The e-mail rows of one person, written with their history and WITHOUT a
    commit (#1590: shared by `apply_email_rows` and the save of the whole
    household). `existing` is {row id: text} — empty text removes the row, other
    text replaces it; a row id that is not this person's is skipped. `new` are the
    texts of rows without an id — empty ones and doubles are skipped; a new row
    becomes the primary address only when the person has none. Returns whether
    anything changed. `source` names who acts in the history (`member_self` when
    the member saves their own household)."""
    from app.domains.audit.api import snapshot_contact_detail
    from app.domains.mdm.models import ContactDetail

    bestaand = {c.id: c for c in person.contact_details if c.contact_type_code == CONTACT.EMAIL}
    gewijzigd = False
    for rij_id, waarde in existing.items():
        rij = bestaand.get(rij_id)
        if rij is None:
            continue  # niet van deze persoon, of net al weggehaald
        if not waarde:
            snapshot_contact_detail(
                db, rij, operation="delete", action="email_removed", source=source, actor=actor
            )
            person.contact_details.remove(rij)
            gewijzigd = True
        elif waarde != rij.value:
            rij.value = waarde
            db.flush()
            snapshot_contact_detail(
                db, rij, operation="update", action="email_edited", source=source, actor=actor
            )
            gewijzigd = True
    # The removals reach the database before a row is added (#1603). A new row
    # becomes the primary address when the person has none — and when the old
    # primary one was just removed in this same save, the unit of work would
    # insert the new primary row BEFORE deleting the old one: two primary rows
    # for a moment, and `uq_contact_details_one_primary_per_type` refuses. Found
    # by a browser test of the one save; the row routes could not do both at once.
    db.flush()
    for waarde in new:
        if not waarde:
            continue
        # Dezelfde waarde twee keer bij één persoon is een vergissing en geen
        # tweede geval; hoofdletterongevoelig, want een mens typt zijn eigen
        # adres niet twee keer identiek.
        al_er = {
            (c.value or "").strip().lower()
            for c in person.contact_details
            if c.contact_type_code == CONTACT.EMAIL
        }
        if waarde.lower() in al_er:
            continue
        wordt_hoofd = not _heeft_hoofdadres(person)
        rij = ContactDetail(
            person_id=person.id, contact_type_code="EMAIL", value=waarde, is_primary=wordt_hoofd
        )
        person.contact_details.append(rij)
        db.flush()
        snapshot_contact_detail(
            db,
            rij,
            operation="insert",
            action="email_promoted" if wordt_hoofd else "email_added",
            source=source,
            actor=actor,
        )
        gewijzigd = True
    return gewijzigd


def make_email_primary(
    db: Session, person_id: int, contact_id: int, *, actor: Optional[str] = None
):
    """Wijs dit adres aan als hoofdadres; het oude wordt een gewoon adres.

    In één beweging, en het oude wordt EERST teruggezet: de databank staat maar
    één hoofdadres per persoon toe
    (`uq_contact_details_one_primary_per_type`, migratie 053, partieel op
    `is_primary = true AND deleted_at IS NULL`). In de andere volgorde zouden er
    even twee zijn en weigert de flush.
    """

    person = _persoon_of_404(db, person_id)
    adressen = [c for c in person.contact_details if c.contact_type_code == CONTACT.EMAIL]
    doel = next((c for c in adressen if c.id == contact_id), None)
    if doel is None:
        from fastapi import HTTPException

        from app.i18n import _

        raise HTTPException(status_code=404, detail=_("Adres niet gevonden"))
    if doel.is_primary:
        return person
    promote_email_row(db, person, doel, actor=actor)
    db.commit()
    db.refresh(person)
    return person


def promote_email_row(
    db: Session, person, doel, *, actor: Optional[str] = None, source: str = "admin_update"
) -> None:
    """Make `doel` this person's primary e-mail address, with the history rows and
    WITHOUT a commit (#1590). The old one is put back FIRST: the database allows one
    primary address per person, so in the other order there would be two for a
    moment and the flush would refuse."""
    from app.domains.audit.api import snapshot_contact_detail

    for rij in person.contact_details:
        if rij.contact_type_code == CONTACT.EMAIL and rij.is_primary and rij is not doel:
            rij.is_primary = False
            db.flush()
            snapshot_contact_detail(
                db, rij, operation="update", action="email_demoted", source=source, actor=actor
            )
    doel.is_primary = True
    db.flush()
    snapshot_contact_detail(
        db, doel, operation="update", action="email_promoted", source=source, actor=actor
    )


def remove_email_address(
    db: Session, person_id: int, contact_id: int, *, actor: Optional[str] = None
):
    """Haal een e-mailadres weg (#1174).

    **Ook het laatste adres mag weg.** Ik had daar eerst een grendel op gezet —
    zonder adres kan een lid zich niet meer aanmelden — maar dat was een eis die
    niemand gevraagd had, en Koen kiest op 27 september 2026 uitdrukkelijk de
    andere kant: *niets aanwijzen, niets weigeren*. Een verkeerd adres moet je
    kunnen weghalen zonder eerst een ander te moeten verzinnen, en de
    audit-snapshot bewaart wat er stond.

    **Verwijder je het hoofdadres, dan komt er geen ander voor in de plaats.** Nul
    hoofdadressen is een geldige toestand — precies wat de databank zegt, want
    `uq_contact_details_one_primary_per_type` is een unieke index en geen
    verplichting.

    Het hoofdadres is een HERKOMST en geen voorkeur: het is het adres dat Raak
    Nationaal in zijn programma heeft (Koen, 27 september 2026). Zelf een ander
    aanwijzen omdat er toevallig een rij overblijft, zou die herkomst verzinnen.
    Een beheerder mág er wél een aanduiden — dat is een bewuste handeling, ze
    wordt geauditeerd, en het nationale programma wordt er met de hand op
    bijgewerkt.
    """
    from app.domains.audit.api import snapshot_contact_detail

    person = _persoon_of_404(db, person_id)
    adressen = sorted(
        (c for c in person.contact_details if c.contact_type_code == CONTACT.EMAIL),
        key=lambda c: c.id or 0,
    )
    doel = next((c for c in adressen if c.id == contact_id), None)
    if doel is None:
        from fastapi import HTTPException

        from app.i18n import _

        raise HTTPException(status_code=404, detail=_("Adres niet gevonden"))
    snapshot_contact_detail(
        db, doel, operation="delete", action="email_removed", source="admin_update", actor=actor
    )
    person.contact_details.remove(doel)
    db.flush()
    db.commit()
    db.refresh(person)
    return person


def upsert_primary_contact(
    db: Session,
    person,
    type_code: str,
    value: Optional[str],
    *,
    action: str,
    source: str,
    is_primary: bool = True,
    apply: bool = True,
    actor: Optional[str] = None,
    adopt_non_primary: bool = False,
) -> bool:
    """Maak, werk bij of verwijder HET HOOFDCONTACT van dit type. Eén bron (#1174).

    `adopt_non_primary` (#1676; the import, for a phone and a mobile number):
    when the person has NO primary row of this type but has other rows of it,
    one of those is the caller's own and becomes the primary row — the one that
    holds this value, else the oldest; the others stay. Once: after it the row
    is primary and the ordinary rule below decides. With an emptied value the
    adopted row is removed, as a primary row is. Without the flag a non-primary
    row is never touched, as before.

    Returns whether it changes something — in dry-run too, where it writes
    nothing (#1308): the import reports a household only when something in it
    changes, and this is where that decision for a contact is made.

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

    van_dit_type = [c for c in person.contact_details if c.contact_type_code == type_code]
    # Which primary row, when a person has more than one of this type (#1676:
    # measured on two environments, for a mobile number — nothing in the
    # database forbids it there): the one that holds this value, else the
    # oldest. Never "the first the relationship happens to give": that has no
    # order, so a re-import could find another row each time and log a change.
    primair = sorted((c for c in van_dit_type if c.is_primary), key=lambda c: c.id or 0)
    hoofd = next((c for c in primair if c.value == value), primair[0] if primair else None)

    if hoofd is None and adopt_non_primary and van_dit_type:
        if not apply:
            return True
        eigen = next((c for c in van_dit_type if c.value == value), None) or min(
            van_dit_type, key=lambda c: c.id or 0
        )
        if not value:
            snapshot_contact_detail(
                db, eigen, operation="delete", action=action, source=source, actor=actor
            )
            person.contact_details.remove(eigen)
            db.flush()
            return True
        eigen.is_primary = True
        eigen.value = value
        db.flush()
        snapshot_contact_detail(
            db, eigen, operation="update", action=action, source=source, actor=actor
        )
        return True

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
                    snapshot_contact_detail(
                        db, zelfde, operation="update", action=action, source=source, actor=actor
                    )
                return True
            if apply:
                # `db.add` en NIET `person.contact_details.append`. Appenden vult de
                # relatie in de sessie, en dan telt ze bij een volgende aanroep als
                # "geladen" terwijl andere relaties van diezelfde persoon dat niet
                # zijn. Gemeten: de import zag daarna `person.address` als None
                # terwijl het adres bestond, en probeerde een tweede adres in te
                # voegen — `uq_addresses_person_id`. Acht bestaande importtests
                # vielen erop om. De import deed dit altijd al met `db.add`; die
                # vorm is hier de veilige.
                nieuw = ContactDetail(
                    person_id=person.id,
                    contact_type_code=type_code,
                    value=value,
                    is_primary=is_primary,
                )
                db.add(nieuw)
                db.flush()
                snapshot_contact_detail(
                    db, nieuw, operation="insert", action=action, source=source, actor=actor
                )
            return True
        if hoofd.value == value and hoofd.is_primary == is_primary:
            return False
        if apply:
            hoofd.value = value
            hoofd.is_primary = is_primary
            db.flush()
            snapshot_contact_detail(
                db, hoofd, operation="update", action=action, source=source, actor=actor
            )
        return True

    if hoofd is None:
        return False
    if not apply:
        return True
    snapshot_contact_detail(
        db, hoofd, operation="delete", action=action, source=source, actor=actor
    )
    person.contact_details.remove(hoofd)
    db.flush()
    return True
    # **Geen promotie.** Er blijft dan géén hoofdcontact over, en dat is een
    # geldige toestand.
    #
    # Ik had hier eerst het oudste overgebleven adres laten promoveren, met het
    # argument dat een lid anders adressen op het scherm houdt en toch geen post
    # krijgt. Koen heeft dat teruggedraaid op 27 september 2026, en zijn reden
    # gaat dieper dan mijn argument: het hoofdadres is geen voorkeur maar een
    # HERKOMST — *"dit is het adres dat Raak Nationaal in zijn programma heeft"*.
    # Wie er zelf een aanwijst omdat er toevallig een rij over is, verzint die
    # herkomst. *"Anders kunnen we dat nooit meer weten. Dan heb ik nog liever
    # dat een lid geen hoofdadres heeft."*
    #
    # Mijn argument vervalt bovendien: geen enkele verzending hangt nog aan het
    # hoofdadres. De nieuwsbrief gaat naar alle adressen, een bevestiging naar
    # het adres op het formulier. Een lid zonder hoofdadres krijgt gewoon alles.


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
    persons = (
        db.query(Person)
        .join(MemberPerson, MemberPerson.person_id == Person.id)
        .filter(MemberPerson.member_id.in_(ids))
        .all()
    )
    addresses = set()
    for person in persons:
        for contact in getattr(person, "contact_details", []) or []:
            if contact.contact_type_code == CONTACT.EMAIL and (contact.value or "").strip():
                addresses.add(contact.value.strip().lower())
    return sorted(addresses)


def gezin_tabs(db, family, viewer_email: str, actief: str) -> list[dict]:
    """De tabbalk van de gezins-recordpagina (golf 9, #913) — zelfde patroon
    als activities.record_tabs: P13 in tabvorm. Overzicht · Inschrijvingen N ·
    Betalingen N (dat laatste alleen voor wie betalingen mag zien, #544).
    De Wijzigingen-tab verviel op Koens vraag (15 sep). Lokale imports:
    auth en payment importeren zelf uit mdm."""
    from app.domains.auth.api import may_view_payments
    from app.domains.payment.api import count_records_for_family
    from app.i18n import _

    tabs = [
        {
            "label": _("Overzicht"),
            "href": f"/admin/leden/gezin/{family.id}",
            "active": actief == "overzicht",
        },
        {
            "label": _("Inschrijvingen") + f" {family_registration_count(db, family.id)}",
            "href": f"/admin/leden/gezin/{family.id}/inschrijvingen",
            "active": actief == "inschrijvingen",
        },
    ]
    if may_view_payments(db, viewer_email):
        n = count_records_for_family(db, family.id)
        tabs.append(
            {
                "label": _("Betalingen") + f" {n}",
                "href": f"/admin/leden/gezin/{family.id}/betalingen",
                "active": actief == "betalingen",
            }
        )
    return tabs


def _family_registration_ids(db, family_id: int) -> list[int]:
    """De inschrijving-ids van een gezin — via dezelfde payable-verzameling
    als de Betalingen-tab (person_id + e-mail-terugval, family_payables is
    de ene bron voor "hoort deze inschrijving bij dit gezin")."""
    from app.domains.payment.api import PayableType, family_payables

    return [i for t, i in family_payables(db, family_id) if t == PayableType.REGISTRATION]


def family_registration_count(db, family_id: int) -> int:
    """Het getal op de Inschrijvingen-tab: één COUNT, zonder geschrapte
    inschrijvingen — dit is een deelnamelijst, geen financieel feit."""
    from sqlalchemy import func

    from app.domains.activities.api import Registration

    ids = _family_registration_ids(db, family_id)
    if not ids:
        return 0
    return db.query(func.count(Registration.id)).filter(Registration.id.in_(ids)).scalar() or 0


def family_registrations(db, family_id: int) -> list[dict]:
    """The registrations of a household, grouped per activity, most recent
    activity first (feedback of 15 September; it replaced the Wijzigingen tab).

    The groups are the input of `activities.api.registration_table` — the one
    builder the activity's tab uses too (K6, #1560): each group names its
    activity, carries the jump link to it, and holds the enriched rows. Sorting
    inside a group is the builder's."""
    from app.domains.activities.api import Registration, enrich_registration
    from app.i18n import _

    ids = _family_registration_ids(db, family_id)
    if not ids:
        return []
    regs = (
        db.query(Registration)
        .filter(Registration.id.in_(ids))
        .order_by(Registration.id.desc())
        .all()
    )
    per_activity: dict = {}
    for reg in regs:
        # Defensive: a registration whose activity is no longer visible
        # (soft-deleted) must not crash the tab; it is not on a list of
        # participants either.
        if reg.activity is None:
            continue
        per_activity.setdefault(reg.activity, []).append(enrich_registration(reg, reg.activity))

    def _last_date(activity):
        dates = [(d.end_date or d.start_date) for d in activity.dates if d.start_date or d.end_date]
        return max(dates) if dates else None

    ordered = sorted(
        per_activity.items(),
        key=lambda pair: (
            _last_date(pair[0]) is not None,
            _last_date(pair[0]) or date.min,
        ),
        reverse=True,
    )
    return [
        {
            "name": activity.name,
            "regs": rows,
            "link": {"label": _("Open activiteit"), "href": f"/admin/activiteiten/{activity.id}"},
        }
        for activity, rows in ordered
    ]


def create_person_for_circle(
    db: Session,
    *,
    first_name: str,
    last_name: str,
    email: str,
    organization_id: int,
    relation_type: str = BOARD_MEETING,
    on_day: Optional[date] = None,
):
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
    # Both names since CR-13 phase 3 (Koen, 29 September 2026): a person always has
    # a first and a last name, here too — `Person` refuses a blank one and the
    # database says the same (`ck_persons_*_not_blank`). Until then one of the two
    # was enough, and a circle person could be stored without a last name.
    if not first_name or not last_name:
        raise ValueError("naam ontbreekt")
    person = Person(first_name=first_name, last_name=last_name)
    db.add(person)
    db.flush()
    if email:
        db.add(
            ContactDetail(
                person_id=person.id, contact_type_code="EMAIL", value=email, is_primary=True
            )
        )
        db.flush()
    add_to_circle(
        db, person.id, organization_id=organization_id, relation_type=relation_type, on_day=on_day
    )
    return person
