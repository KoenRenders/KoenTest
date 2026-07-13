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
