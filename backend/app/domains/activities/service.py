"""Leesbewerkingen op activiteiten (#635 I).

De schermen haalden activiteiten, onderdelen en inschrijvingen met eigen queries
op. Kleine queries, maar ze dragen wel de vraag "bestaat dit?" — en die hoort één
antwoord te hebben, niet vier.
"""
from typing import Optional

from app.domains.activities.models import (Activity, ActivitySubRegistration,
                                           Registration)


def get_activity(db, activity_id: int,
                 include_deleted: bool = False) -> Optional[Activity]:
    query = db.query(Activity)
    if include_deleted:
        query = query.execution_options(include_deleted=True)
    return query.filter(Activity.id == activity_id).first()


def get_component(db, component_id: int,
                  activity_id: Optional[int] = None) -> Optional[ActivitySubRegistration]:
    """Een onderdeel, eventueel binnen één activiteit.

    Met `activity_id` erbij is dit meteen de controle dat het onderdeel écht bij
    die activiteit hoort — anders zou /activiteiten/1/inschrijven/99 het onderdeel
    van een andere activiteit tonen.
    """
    query = db.query(ActivitySubRegistration).filter(
        ActivitySubRegistration.id == component_id)
    if activity_id is not None:
        query = query.filter(ActivitySubRegistration.activity_id == activity_id)
    return query.first()


def get_registration(db, registration_id: int,
                     include_deleted: bool = False) -> Optional[Registration]:
    """Een inschrijving. Met `include_deleted` ook een geschrapte.

    Dat laatste is nodig op het betalingenscherm: een betaling is een financieel
    feit, dus de bewaarde naam moet zichtbaar blijven ook als de inschrijving
    geschrapt is (#190)."""
    query = db.query(Registration)
    if include_deleted:
        query = query.execution_options(include_deleted=True)
    return query.filter(Registration.id == registration_id).first()
