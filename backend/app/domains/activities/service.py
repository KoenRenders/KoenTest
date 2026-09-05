"""Lees- én schrijfbewerkingen op activiteiten (#635 I, #679).

De schermen haalden activiteiten, onderdelen en inschrijvingen met eigen queries
op. Kleine queries, maar ze dragen wel de vraag "bestaat dit?" — en die hoort één
antwoord te hebben, niet vier.

Sinds #679 verhuizen ook de CRUD-bewerkingen hierheen, in batches. Het is een
SCHEIDING, geen verplaatsing: wat in een routerfunctie zat, is een mengsel van
HTTP-afhandeling (404's, `Depends`, de responsvorm) en domeinregels (volgorde
normaliseren, totalen reconciliëren, audit-snapshots). Alleen het tweede hoort
hier. De router houdt zijn 404 en zijn responsemodel; de service kent geen HTTP.

De transactiegrens ligt hier (§635 regel 2): de service commit, het scherm niet.
Zo volgt élke ingang — JSON-router, UI-route, script — dezelfde regel.
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


def create_activity(db, *, name: str, location=None, poster_url=None,
                    members_only: bool = False, dates=(), actor=None) -> Activity:
    """Maak een activiteit met haar eerste datums (#679, batch 1).

    De audit-snapshots horen bij de mutatie, niet bij de route: een activiteit die
    buiten de JSON-router om wordt aangemaakt, hoort dezelfde geschiedenis te
    krijgen. `dates` bevat objecten met start_date/end_date/start_time/end_time —
    de Pydantic-vorm van de router past daarop, maar de service eist ze niet.
    """
    from app.domains.audit.api import snapshot_activity, snapshot_activity_date

    activity = Activity(name=name, location=location, poster_url=poster_url,
                        members_only=bool(members_only))
    db.add(activity)
    db.flush()
    snapshot_activity(db, activity, operation="insert", action="activity_created",
                      source="admin_manual", actor=actor)

    for datum in dates:
        ad = ActivityDate(
            activity_id=activity.id,
            start_date=datum.start_date,
            end_date=getattr(datum, "end_date", None),
            start_time=getattr(datum, "start_time", None),
            end_time=getattr(datum, "end_time", None),
        )
        db.add(ad)
        db.flush()
        snapshot_activity_date(db, ad, operation="insert", action="activity_created",
                               source="admin_manual", actor=actor)
    db.commit()
    return activity


def update_activity(db, activity_id: int, velden: dict, *, actor=None) -> Optional[Activity]:
    """Werk de velden van een activiteit bij. Geeft None als ze niet bestaat.

    De aanroeper beslist wat een ontbrekende activiteit betekent — de JSON-router
    maakt er een 404 van, een script misschien iets anders. De service kent geen
    HTTP-statuscodes.
    """
    from app.domains.audit.api import snapshot_activity

    activity = _activity_met_boom(db, activity_id)
    if activity is None:
        return None
    for veld, waarde in velden.items():
        setattr(activity, veld, waarde)
    snapshot_activity(db, activity, operation="update", action="activity_updated",
                      source="admin_manual", actor=actor)
    db.commit()
    db.refresh(activity)
    return activity


def delete_activity(db, activity_id: int, *, actor=None) -> bool:
    """Soft delete van de hele boom (#166). Geeft False als ze niet bestaat.

    Datums, onderdelen, producten, inschrijvingen en bestelregels gaan mee.
    Betalingen NIET: die zijn een financieel feit en blijven bestaan — dat is
    dezelfde regel die #667 met een gate vastlegde.
    """
    from app.domains.audit.api import (snapshot_activity, snapshot_activity_date,
                                       snapshot_component, snapshot_product)
    from app.soft_delete import soft_delete

    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if activity is None:
        return False
    for d in activity.dates:
        snapshot_activity_date(db, d, operation="delete", action="activity_deleted",
                               source="admin_manual", actor=actor)
        soft_delete(d)
    for comp in activity.sub_registrations:
        for p in comp.products:
            snapshot_product(db, p, operation="delete", action="activity_deleted",
                             source="admin_manual", actor=actor)
            soft_delete(p)
        snapshot_component(db, comp, operation="delete", action="activity_deleted",
                           source="admin_manual", actor=actor)
        soft_delete(comp)
    for reg in activity.registrations:
        for item in reg.items:
            soft_delete(item)
        soft_delete(reg)
    snapshot_activity(db, activity, operation="delete", action="activity_deleted",
                      source="admin_manual", actor=actor)
    soft_delete(activity)
    db.commit()
    return True


def _activity_met_boom(db, activity_id: int) -> Optional[Activity]:
    """Eén activiteit met haar datums, onderdelen en producten in één keer."""
    from sqlalchemy.orm import selectinload

    return (db.query(Activity)
            .options(selectinload(Activity.dates),
                     selectinload(Activity.sub_registrations)
                     .selectinload(ActivitySubRegistration.products))
            .filter(Activity.id == activity_id)
            .first())


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


def registrations_without_component_count(db, activity_id: int) -> int:
    """Inschrijvingen op deze activiteit die aan geen enkel onderdeel hangen (#650).

    `Registration.component_id` is nullable met `ondelete="SET NULL"`: verwijder je
    een onderdeel, dan blijven de inschrijvingen bestaan, maar zonder onderdeel.
    Staat de knop "Toon inschrijvingen" enkel per onderdeel, dan zijn ze via geen
    enkele knop meer te bereiken — onzichtbaar terwijl ze in de databank staan.
    Dit getal bepaalt of het scherm daar een aparte kaart voor toont.

    De soft-delete- en tenantfilters komen van `with_loader_criteria`, dus een
    geschrapte inschrijving telt niet mee.
    """
    return (db.query(func.count(Registration.id))
            .filter(Registration.activity_id == activity_id,
                    Registration.component_id.is_(None))
            .scalar() or 0)
