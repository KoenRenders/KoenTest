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


def add_activity_date(db, activity_id: int, gegevens, *, actor=None) -> Optional[ActivityDate]:
    """Voeg een datum toe. None als de activiteit niet bestaat (#679, batch 2)."""
    from app.domains.audit.api import snapshot_activity_date

    if db.query(Activity).filter(Activity.id == activity_id).first() is None:
        return None
    ad = ActivityDate(
        activity_id=activity_id,
        start_date=gegevens.start_date,
        end_date=getattr(gegevens, "end_date", None),
        start_time=getattr(gegevens, "start_time", None),
        end_time=getattr(gegevens, "end_time", None),
    )
    db.add(ad)
    db.flush()
    snapshot_activity_date(db, ad, operation="insert", action="date_created",
                           source="admin_manual", actor=actor)
    db.commit()
    db.refresh(ad)
    return ad


def update_activity_date(db, activity_id: int, date_id: int, velden: dict, *,
                         actor=None) -> Optional[ActivityDate]:
    """Werk een datum bij. None als ze niet bij deze activiteit hoort.

    Het activiteit-id hoort bij de sleutel en niet bij de HTTP-laag: een datum van
    activiteit A mag je niet via activiteit B kunnen bewerken, ongeacht welke
    ingang het probeert.
    """
    from app.domains.audit.api import snapshot_activity_date

    ad = _datum(db, activity_id, date_id)
    if ad is None:
        return None
    for veld, waarde in velden.items():
        setattr(ad, veld, waarde)
    snapshot_activity_date(db, ad, operation="update", action="date_updated",
                           source="admin_manual", actor=actor)
    db.commit()
    db.refresh(ad)
    return ad


def delete_activity_date(db, activity_id: int, date_id: int, *, actor=None) -> bool:
    """Soft delete van één datum. False als ze niet bij deze activiteit hoort."""
    from app.domains.audit.api import snapshot_activity_date
    from app.soft_delete import soft_delete

    ad = _datum(db, activity_id, date_id)
    if ad is None:
        return False
    snapshot_activity_date(db, ad, operation="delete", action="date_deleted",
                           source="admin_manual", actor=actor)
    soft_delete(ad)
    db.commit()
    return True


def _datum(db, activity_id: int, date_id: int) -> Optional[ActivityDate]:
    return (db.query(ActivityDate)
            .filter(ActivityDate.id == date_id,
                    ActivityDate.activity_id == activity_id)
            .first())


class ActiviteitFout(ValueError):
    """Een domeinregel is geschonden (#679, batch 3).

    Geen HTTPException: die hoort bij de ingang, niet bij de regel. De router
    vertaalt hem naar een 422, een script mag er iets anders mee doen. Zonder dit
    type zou de regel "gratis én ter plaatse kan niet" in de route blijven staan,
    en dan geldt ze niet voor wie de service rechtstreeks aanroept.
    """


def add_component(db, activity_id: int, gegevens, *, actor=None):
    """Voeg een onderdeel toe. None als de activiteit niet bestaat."""
    from app.domains.audit.api import snapshot_component

    if db.query(Activity).filter(Activity.id == activity_id).first() is None:
        return None
    component = ActivitySubRegistration(
        activity_id=activity_id,
        name=gegevens.name,
        team_name_required=gegevens.team_name_required,
        sort_order=gegevens.sort_order,
        external_register_url=gegevens.external_register_url,
        external_registrations_url=gegevens.external_registrations_url,
        info_url=gegevens.info_url,
        max_participants=gegevens.max_participants,
        # Verplichte FK, bewaard voor DB-compatibiliteit; sinds de v2.0-unificatie
        # vertakt er niets meer op dit veld.
        registration_type_code="INDIVIDUAL",
        price=0,
        is_free=True,
    )
    db.add(component)
    db.flush()
    snapshot_component(db, component, operation="insert", action="component_created",
                       source="admin_manual", actor=actor)
    db.commit()
    db.refresh(component)
    return component


def update_component(db, activity_id: int, component_id: int, velden: dict, *,
                     actor=None):
    """Werk een onderdeel bij. None als het niet bij deze activiteit hoort."""
    from app.domains.audit.api import snapshot_component

    component = get_component(db, component_id, activity_id=activity_id)
    if component is None:
        return None
    for veld, waarde in velden.items():
        setattr(component, veld, waarde)
    snapshot_component(db, component, operation="update", action="component_updated",
                       source="admin_manual", actor=actor)
    db.commit()
    db.refresh(component)
    return component


def delete_component(db, activity_id: int, component_id: int, *, actor=None) -> bool:
    """Soft delete van een onderdeel én zijn producten. False als het niet bestaat."""
    from app.domains.audit.api import snapshot_component, snapshot_product
    from app.soft_delete import soft_delete

    component = get_component(db, component_id, activity_id=activity_id)
    if component is None:
        return False
    for p in component.products:
        snapshot_product(db, p, operation="delete", action="component_deleted",
                         source="admin_manual", actor=actor)
        soft_delete(p)
    snapshot_component(db, component, operation="delete", action="component_deleted",
                       source="admin_manual", actor=actor)
    soft_delete(component)
    db.commit()
    return True


def _controleer_afrekening(is_free, pay_on_site) -> None:
    """Gratis én ter plaatse te betalen sluiten elkaar uit.

    Een domeinregel, dus hier en niet in de route: ze geldt voor élke ingang.
    """
    if is_free and pay_on_site:
        from app.i18n import _ as vertaal

        raise ActiviteitFout(vertaal(
            "Een product kan niet tegelijk gratis én ter plaatse te betalen zijn."))


def add_product(db, activity_id: int, component_id: int, gegevens, *, actor=None):
    """Voeg een product toe. None als het onderdeel niet bij de activiteit hoort."""
    from app.domains.activities.models import ActivityProduct
    from app.domains.audit.api import snapshot_product

    if get_component(db, component_id, activity_id=activity_id) is None:
        return None
    _controleer_afrekening(gegevens.is_free, gegevens.pay_on_site)
    product = ActivityProduct(
        component_id=component_id,
        name=gegevens.name,
        price=gegevens.price,
        member_price=gegevens.member_price,
        is_free=gegevens.is_free,
        pay_on_site=gegevens.pay_on_site,
        max_participants=gegevens.max_participants,
        sort_order=gegevens.sort_order,
    )
    db.add(product)
    db.flush()
    snapshot_product(db, product, operation="insert", action="product_created",
                     source="admin_manual", actor=actor)
    db.commit()
    db.refresh(product)
    return product


def update_product(db, component_id: int, product_id: int, velden: dict, *, actor=None):
    """Werk een product bij. None als het niet bij dit onderdeel hoort."""
    from app.domains.audit.api import snapshot_product

    product = _product(db, component_id, product_id)
    if product is None:
        return None
    for veld, waarde in velden.items():
        setattr(product, veld, waarde)
    # Ná het toepassen: de combinatie kan ook ontstaan door één veld te wijzigen.
    _controleer_afrekening(product.is_free, product.pay_on_site)
    snapshot_product(db, product, operation="update", action="product_updated",
                     source="admin_manual", actor=actor)
    db.commit()
    db.refresh(product)
    return product


def delete_product(db, component_id: int, product_id: int, *, actor=None) -> bool:
    """Soft delete van één product. False als het niet bij dit onderdeel hoort."""
    from app.domains.audit.api import snapshot_product
    from app.soft_delete import soft_delete

    product = _product(db, component_id, product_id)
    if product is None:
        return False
    snapshot_product(db, product, operation="delete", action="product_deleted",
                     source="admin_manual", actor=actor)
    soft_delete(product)
    db.commit()
    return True


def _product(db, component_id: int, product_id: int):
    from app.domains.activities.models import ActivityProduct

    return (db.query(ActivityProduct)
            .filter(ActivityProduct.id == product_id,
                    ActivityProduct.component_id == component_id)
            .first())


# ── Bestelregels en inschrijvingen (#679, batch 4) ────────────────────────────

def _registratie(db, activity_id: int, registration_id: int):
    return (db.query(Registration)
            .filter(Registration.id == registration_id,
                    Registration.activity_id == activity_id)
            .first())


def _regel(db, registration_id: int, item_id: int):
    from app.domains.activities.models import RegistrationItem

    return (db.query(RegistrationItem)
            .filter(RegistrationItem.id == item_id,
                    RegistrationItem.registration_id == registration_id)
            .first())


def controleer_bestelproduct(db, activity_id: int, registration, product_id: int):
    """Een bestelregel mag enkel een product van deze activiteit/dit onderdeel dragen.

    Domeinregel, dus hier: ze beschermt de koppeling tussen inschrijving en
    aanbod, en die moet gelden ongeacht welke ingang een regel toevoegt. Geeft het
    product terug; `ActiviteitFout` als de koppeling niet klopt, None als het
    product niet bestaat — twee verschillende dingen, dus twee verschillende
    antwoorden.
    """
    from app.domains.activities.models import ActivityProduct
    from app.i18n import _ as vertaal

    product = db.query(ActivityProduct).filter(
        ActivityProduct.id == product_id).first()
    if product is None:
        return None
    comp = get_component(db, product.component_id)
    if comp is None or comp.activity_id != activity_id:
        raise ActiviteitFout(vertaal("Product hoort niet bij deze activiteit."))
    if (registration.component_id is not None
            and product.component_id != registration.component_id):
        raise ActiviteitFout(vertaal(
            "Product hoort niet bij het onderdeel van deze inschrijving."))
    return product


def add_order_line(db, activity_id: int, registration_id: int, product_id: int,
                   quantity: int, *, actor=None):
    """Voeg een bestelregel toe, of hoog een bestaande regel op (#197).

    Geeft de inschrijving terug, of None als activiteit/inschrijving/product niet
    bestaat. Het reconciliëren van de betaalposten doet de aanroeper met
    `reconcile_registration_charges` — dat is payment-domein, geen activiteiten.
    """
    from app.domains.activities.models import RegistrationItem
    from app.domains.audit.api import snapshot_registration_item
    from app.i18n import _ as vertaal

    reg = _registratie(db, activity_id, registration_id)
    if reg is None:
        return None
    if quantity < 1:
        raise ActiviteitFout(vertaal("Aantal moet minstens 1 zijn."))
    if controleer_bestelproduct(db, activity_id, reg, product_id) is None:
        return None

    bestaand = (db.query(RegistrationItem)
                .filter(RegistrationItem.registration_id == reg.id,
                        RegistrationItem.product_id == product_id)
                .first())
    if bestaand is not None:
        # #197: geen tweede regel voor hetzelfde product, maar optellen.
        bestaand.quantity += quantity
        db.flush()
        snapshot_registration_item(db, bestaand, operation="update",
                                   action="order_changed", source="admin_manual",
                                   actor=actor)
    else:
        item = RegistrationItem(registration_id=reg.id, product_id=product_id,
                                quantity=quantity)
        db.add(item)
        db.flush()
        snapshot_registration_item(db, item, operation="insert",
                                   action="order_changed", source="admin_manual",
                                   actor=actor)
    db.commit()
    _herbereken(db, reg, actor)
    return reg


def update_order_line(db, activity_id: int, registration_id: int, item_id: int,
                      *, product_id=None, quantity=None, actor=None):
    """Wijzig een bestelregel. None als activiteit/inschrijving/regel niet bestaat."""
    from app.domains.audit.api import snapshot_registration_item
    from app.i18n import _ as vertaal

    reg = _registratie(db, activity_id, registration_id)
    if reg is None:
        return None
    item = _regel(db, reg.id, item_id)
    if item is None:
        return None
    if product_id is not None:
        if controleer_bestelproduct(db, activity_id, reg, product_id) is None:
            return None
        item.product_id = product_id
    if quantity is not None:
        if quantity < 1:
            raise ActiviteitFout(vertaal(
                "Aantal moet minstens 1 zijn; verwijder de regel om ze te schrappen."))
        item.quantity = quantity
    db.flush()
    snapshot_registration_item(db, item, operation="update", action="order_changed",
                              source="admin_manual", actor=actor)
    db.commit()
    _herbereken(db, reg, actor)
    return reg


def delete_order_line(db, activity_id: int, registration_id: int, item_id: int, *,
                      actor=None):
    """Soft delete van één bestelregel. None als ze niet gevonden wordt.

    Snapshot vóór het schrappen (#84/#166): de bronrij blijft bestaan maar wordt
    gemarkeerd, en de globale filter sluit haar uit bij de saldo-herberekening.
    """
    from app.domains.audit.api import snapshot_registration_item
    from app.soft_delete import soft_delete

    reg = _registratie(db, activity_id, registration_id)
    if reg is None:
        return None
    item = _regel(db, reg.id, item_id)
    if item is None:
        return None
    snapshot_registration_item(db, item, operation="delete", action="order_changed",
                              source="admin_manual", actor=actor)
    soft_delete(item)
    db.commit()
    _herbereken(db, reg, actor)
    return reg


def _herbereken(db, reg, actor) -> None:
    """De betaalposten volgen de bestelling (#185).

    Dit hoorde in `_order_edit_result` in de router, samen met het vormgeven van
    het antwoord. Twee verschillende dingen: dát de charges herrekend worden is een
    domeinregel — wie een bestelregel wijzigt zonder te reconciliëren laat het
    saldo stil verkeerd staan — en die regel moet gelden voor élke ingang, ook een
    scherm dat de service rechtstreeks aanroept.

    `reconcile_registration_charges` is integraal en dus idempotent: nog eens
    aanroepen verandert niets.
    """
    from app.domains.payment.api import reconcile_registration_charges

    db.refresh(reg)
    reconcile_registration_charges(db, reg, audit_actor=actor)
    db.commit()
    db.refresh(reg)


def update_registration_contact(db, activity_id: int, registration_id: int,
                                gezet: dict, *, actor=None):
    """Corrigeer contactgegevens en/of opmerking (#283, uitgebreid #624).

    Raakt bestelregels, saldo en OGM NIET aan — dit is geen geldwijziging. Leeg of
    enkel witruimte wordt NULL. Enkel meegestuurde velden veranderen, zodat de
    oude #283-aanroep (alleen `remarks`) blijft werken.

    Alleen bij een échte wijziging een snapshot: een opslag zonder verschil hoort
    geen rij in het logboek op te leveren, anders wordt de geschiedenis ruis.
    """
    from app.domains.audit.api import snapshot_registration

    reg = _registratie(db, activity_id, registration_id)
    if reg is None:
        return None
    gewijzigd = False
    for veld in ("contact_name", "contact_email", "phone", "remarks"):
        if veld not in gezet:
            continue
        waarde = (str(gezet[veld]) if gezet[veld] is not None else "").strip() or None
        if getattr(reg, veld) != waarde:
            setattr(reg, veld, waarde)
            gewijzigd = True
    if gewijzigd:
        db.flush()
        snapshot_registration(db, reg, operation="update",
                              action="registration_contact_updated",
                              source="admin_manual", actor=actor)
    db.commit()
    db.refresh(reg)
    return reg


def delete_registration(db, activity_id: int, registration_id: int, *, actor=None) -> bool:
    """Soft delete van een inschrijving én haar bestelregels (#313).

    Raakt de betaling NIET aan: een PaymentRecord is een financieel feit en blijft
    bestaan én zichtbaar (de verrijking haalt soft-deleted inschrijvingen op via
    include_deleted, #190). De bestelregels gaan wél mee, met snapshot, zodat ze
    niet in aantal- en saldoberekeningen lekken (#194).

    Het reconciliëren gebeurt vóór het schrappen van de inschrijving zelf: het
    besteltotaal is dan 0, dus een reeds betaald bedrag wordt een
    terugbetaalverplichting en een onbetaalde charge verdwijnt (#185/#313).
    """
    from app.domains.audit.api import snapshot_registration_item
    from app.domains.payment.api import reconcile_registration_charges
    from app.soft_delete import soft_delete

    reg = _registratie(db, activity_id, registration_id)
    if reg is None:
        return False
    for item in list(reg.items):
        if getattr(item, "deleted_at", None) is None:
            snapshot_registration_item(db, item, operation="delete",
                                       action="order_changed",
                                       source="admin_manual", actor=actor)
            soft_delete(item)
    db.commit()
    db.refresh(reg)
    reconcile_registration_charges(db, reg, audit_actor=actor)
    soft_delete(reg)
    db.commit()
    return True


# ── Export (#679, batch 5) ────────────────────────────────────────────────────

def component_export(db, activity_id: int, component_id: int):
    """De .ods van één onderdeel, plus een veilige bestandsnaam.

    De opbouw zelf staat al in `activities/export.py` en verhuist niet — die was
    nooit routerlogica. Wat hier bijkomt is het OPZOEKEN (bestaat dit onderdeel bij
    deze activiteit?) en het samenstellen van de naam. Dat laatste is geen HTTP:
    dezelfde naam hoort in een e-mailbijlage of een bestand op schijf te staan.

    Geeft (inhoud, bestandsnaam) terug, of None als de activiteit of het onderdeel
    niet bestaat.
    """
    import re

    from app.domains.activities.export import build_component_export_ods

    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if activity is None:
        return None
    component = get_component(db, component_id, activity_id=activity_id)
    if component is None:
        return None
    inhoud = build_component_export_ods(db, activity, component)
    ruw = f"{activity.name}-{component.name}"
    veilig = re.sub(r"[^A-Za-z0-9_-]+", "_", ruw).strip("_") or "export"
    return inhoud, f"{veilig}.ods"


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


def enrich_registration(reg, activity) -> dict:
    """Eén inschrijving met de namen erbij die het scherm toont (#679, batch 6).

    De regels dragen enkel een `product_id`; product- en onderdeelnaam komen uit de
    activiteitenboom. Hangt een regel aan een product dat inmiddels weg is, dan valt
    de onderdeelnaam terug op die van de inschrijving zelf.
    """
    product_map = {}
    comp_map = {c.id: c.name for c in activity.sub_registrations}
    for comp in activity.sub_registrations:
        for p in comp.products:
            product_map[p.id] = (p.name, comp.name)
    component_name = comp_map.get(reg.component_id) if reg.component_id else None
    items = []
    for item in reg.items:
        pname, cname = product_map.get(item.product_id, (None, component_name))
        items.append({
            "id": item.id,
            "product_id": item.product_id,
            "quantity": item.quantity,
            "product_name": pname,
            "component_name": cname or component_name,
        })
    return {
        "id": reg.id,
        "activity_id": reg.activity_id,
        "component_id": reg.component_id,
        "person_id": reg.person_id,
        "registered_at": reg.registered_at,
        "contact_name": reg.contact_name,
        "contact_email": reg.contact_email,
        "phone": reg.phone,
        "team_name": reg.team_name,
        "payment_method": getattr(reg, "payment_method", None),
        "remarks": getattr(reg, "remarks", None),
        "items": items,
    }


def registrations_for(db, activity_id: int, *, component_id: Optional[int] = None,
                      without_component: bool = False) -> Optional[list[dict]]:
    """De inschrijvingen van één activiteit, verrijkt. None als ze niet bestaat.

    Expliciete, stabiele sortering (#285): zonder ORDER BY geeft Postgres de rijen
    in heap-volgorde terug, waardoor een bewerkte inschrijving (UPDATE, bv. een
    opmerking, #283) naar onderen springt. Oud → nieuw, id als tiebreaker.

    Het filter hoort hier, niet in het scherm (#650). Twee losse vragen, want ze
    zijn niet hetzelfde: één onderdeel, of juist de inschrijvingen die aan GEEN
    onderdeel hangen. Die laatste bestaan — `component_id` is nullable met
    `ondelete="SET NULL"` — en zouden zonder eigen filter via geen enkele knop meer
    bereikbaar zijn.
    """
    activity = _activity_met_boom(db, activity_id)
    if activity is None:
        return None
    vraag = db.query(Registration).filter(Registration.activity_id == activity.id)
    if without_component:
        vraag = vraag.filter(Registration.component_id.is_(None))
    elif component_id is not None:
        vraag = vraag.filter(Registration.component_id == component_id)
    regs = (vraag
            .order_by(Registration.registered_at.asc(), Registration.id.asc())
            .all())
    return [enrich_registration(r, activity) for r in regs]
