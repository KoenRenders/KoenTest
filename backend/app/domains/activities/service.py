"""Leesbewerkingen op activiteiten (#635 I).

De schermen haalden activiteiten, onderdelen en inschrijvingen met eigen queries
op. Kleine queries, maar ze dragen wel de vraag "bestaat dit?" — en die hoort één
antwoord te hebben, niet vier.
"""
from datetime import date
from typing import NamedTuple, Optional

from sqlalchemy import func, nulls_last

from app.domains.activities.models import (Activity, ActivityDate,
                                           ActivitySubRegistration, Registration)


class ActivityOption(NamedTuple):
    """Eén regel in een activiteiten-keuzelijst."""

    id: int
    name: str
    first_date: Optional[date]


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


def activity_options(db) -> list[ActivityOption]:
    """Élke activiteit als (id, naam, vroegste datum) — voor een keuzelijst.

    Bestaat omdat een `<select>` iets anders nodig heeft dan een lijstscherm. Het
    mediabeheer vulde zijn upload-dropdown met `list_activities(scope="all")`, en
    die doet eager loading van datums, onderdelen én producten, gecorreleerde
    subqueries voor de datumsortering en de bezettingsberekening per onderdeel.
    Met ~169 activiteiten werden zo honderden rijen opgehaald om er drie velden
    uit te lezen: `/admin/media` zat op p95 578 ms, tegen 9–122 ms voor de tien
    andere adminroutes (#645 stap C). Geen N+1 — een lijstbewerking hergebruikt
    voor een dropdown.

    Eén query, geen eager loading. `sort_date` bestaat niet als kolom (het wordt
    in `router._build_response` in Python berekend uit de geladen datums), dus het
    jaar komt hier uit `min(start_date)` via een outerjoin.

    **Het jaar is het vroegste, niet de eerstvolgende datum.** Voor de grote
    meerderheid — activiteiten die voorbij zijn — is dat exact wat er vandaag
    staat: zonder toekomstige datum viel `sort_date` al terug op de eerste datum.
    Het verschil verschijnt alleen bij een activiteit die nog een datum in de
    toekomst heeft én eerder begon. Voor een label is het vroegste jaar beter: het
    verschuift niet naarmate de tijd vordert, en een keuzelijst gebruik je om twee
    gelijknamige activiteiten uit elkaar te houden ("Kerstradio (2024)" vs.
    "(2025)"). "De eerstvolgende datum" is een vraag van de publieke lijst — wat
    komt eraan — en heeft in een uploadscherm geen betekenis.

    Volgorde: meest recente eerst, activiteiten zonder datum achteraan. Je koppelt
    foto's aan wat net geweest is.

    De globale filters op soft-delete en tenant komen van `with_loader_criteria`
    (app/soft_delete.py, app/kernel/tenancy.py); die gelden ook voor de
    outerjoin — vandaar geen handmatige `deleted_at`-check hier.
    """
    rijen = (db.query(Activity.id, Activity.name,
                      func.min(ActivityDate.start_date))
             .outerjoin(ActivityDate, ActivityDate.activity_id == Activity.id)
             .group_by(Activity.id, Activity.name)
             .order_by(nulls_last(func.min(ActivityDate.start_date).desc()),
                       Activity.name)
             .all())
    return [ActivityOption(id=rij[0], name=rij[1], first_date=rij[2])
            for rij in rijen]
