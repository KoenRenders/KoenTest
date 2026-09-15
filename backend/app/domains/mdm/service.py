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
from typing import NamedTuple, Optional

from sqlalchemy import or_
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
    parts: set[str] = set()
    for first, last in rows:
        for value in (first, last):
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
    """The person's e-mail address, or None. `EMAIL` is the code the whole code
    base uses for it (auth, activities, audit all read it this way)."""
    for contact in getattr(person, "contact_details", []) or []:
        if contact.contact_type_code == "EMAIL" and contact.value:
            return contact.value
    return None


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


def gezin_tabs(db, family, viewer_email: str, actief: str) -> list[dict]:
    """De tabbalk van de gezins-recordpagina (golf 9, #913) — zelfde patroon
    als activities.record_tabs: P13 in tabvorm. Betalingen alleen met FINANCE
    (#544); Wijzigingen zonder aantal — de feed over tien history-tabellen
    materialiseren voor één getal is de prijs niet waard. Lokale imports:
    auth en payment importeren zelf uit mdm."""
    from app.i18n import _
    from app.domains.auth.api import may_view_payments
    from app.domains.payment.api import count_records_for_family

    tabs = [
        {"label": _("Overzicht"),
         "href": f"/admin/leden/gezin/{family.id}",
         "active": actief == "overzicht"},
    ]
    if may_view_payments(db, viewer_email):
        n = count_records_for_family(db, family.id)
        tabs.append({"label": _("Betalingen") + f" {n}",
                     "href": f"/admin/leden/gezin/{family.id}/betalingen",
                     "active": actief == "betalingen"})
    tabs.append({"label": _("Wijzigingen"),
                 "href": f"/admin/leden/gezin/{family.id}/wijzigingen",
                 "active": actief == "wijzigingen"})
    return tabs


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
