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
from typing import Optional

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
