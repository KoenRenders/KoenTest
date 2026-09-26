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
from enum import Enum
from typing import NamedTuple, Optional

from sqlalchemy import func, nulls_last
from app.kernel.codes import code_of
from app.domains.mdm.api import CONTACT

from app.domains.activities.models import (ActiviteitFout, Activity, ActivityDate,
                                           ActivitySubRegistration, Registration)


class RegistrationState(str, Enum):
    """Whether an activity accepts a NEW registration, and if not, why (#974).

    The reason matters as much as the answer: the refusal message and the badge on
    the card say different things for "this has passed" and "registrations closed
    on 1 October", and a caller that only gets a boolean will guess.
    """

    OPEN = "open"
    #: No date of the activity lies today or later.
    PAST = "past"
    #: The registration deadline has passed.
    CLOSED = "closed"
    #: The activity is cancelled. Until #974 only the public card knew this: it
    #: hid the button, while the server accepted a form that was posted anyway.
    #: Koen decided on 16 September 2026 that the server refuses too.
    CANCELLED = "cancelled"


def _effective_end(ad: ActivityDate) -> date:
    return ad.end_date or ad.start_date


def _deadline_van(component) -> Optional[date]:
    return getattr(component, "registration_closes_on", None)


def open_deadlines(activity: Activity) -> list[date]:
    """De uiterste inschrijfdatums van deze activiteit, zonder dubbels (#1053).

    Eén datum in de lijst betekent: elk onderdeel dat er een heeft, heeft
    dezelfde — dat is het gewone geval (76 van de 86 activiteiten met onderdelen
    op HDEV hebben er precies één). Meer dan één betekent dat de datum bij het
    onderdeel hoort en niet bovenaan de kaart.
    """
    return sorted({d for d in (_deadline_van(c) for c in activity.sub_registrations)
                   if d is not None})


def shared_deadline(activity: Activity) -> Optional[date]:
    """De ene uiterste datum die voor ÉLK onderdeel geldt, of None (#1053).

    Twee schermen stellen dezelfde vraag — de rail van het beheerdetail en de
    publieke kaart (#1051) — en ze moeten hem niet elk op hun eigen manier
    beantwoorden. None betekent hier twee dingen die beide "geen ene datum" zijn:
    geen enkel onderdeel heeft er een, of ze verschillen. Welke van de twee zegt
    :func:`open_deadlines`.
    """
    onderdelen = list(activity.sub_registrations)
    if not onderdelen:
        return None
    datums = {_deadline_van(c) for c in onderdelen}
    return datums.pop() if len(datums) == 1 else None


#: Hoeveel dagen vóór de uiterste datum de kaart de regel oranje kleurt (#1051).
#: Zeven, zodat "nog deze week" klopt: op de dag zelf is het verschil 0.
DEADLINE_ATTENTIE_DAGEN = 7


def deadline_is_near(deadline: Optional[date], *, today: Optional[date] = None) -> bool:
    """Valt de uiterste datum binnen de laatste week? (#1051)

    Een regel en dus hier: ze hangt af van welke dag het vandaag is, en de
    Belgische dag is dezelfde als die van de poort — anders kleurt de kaart een
    paar uur eerder of later dan er werkelijk gesloten wordt.
    """
    from app.kernel.clock import belgian_today

    if deadline is None:
        return False
    vandaag = today or belgian_today()
    return 0 <= (deadline - vandaag).days <= DEADLINE_ATTENTIE_DAGEN


def card_deadline(activity, *, today: Optional[date] = None) -> Optional[date]:
    """De ene uiterste datum die de publieke kaart onder datum en locatie zet,
    of None wanneer er geen zo'n datum is (#1053, dat de aanpak van #1051 vervangt).

    "Open" is hier smaller dan in :func:`registration_state`: een volzet onderdeel
    neemt geen inschrijvingen meer aan, dus zijn datum hoort niet meer op de kaart —
    dat was al zo vóór deze verhuizing. Delen alle open onderdelen dezelfde datum,
    dan is dat de datum van de kaart; verschillen ze, dan hoort elke datum bij haar
    eigen onderdeel en geeft deze functie None.

    `is_full` wordt via `getattr` gelezen omdat alleen het ANTWOORD-onderdeel het
    draagt (de router vult het na de bezettingstelling); op een kaal ORM-onderdeel
    telt het als niet-volzet. De toestand wordt wél opnieuw berekend in plaats van
    afgelezen, zodat deze functie hetzelfde antwoord geeft op beide vormen.
    """
    openstaand = [c for c in activity.sub_registrations
                  if registration_state(activity, component=c,
                                        today=today) is RegistrationState.OPEN
                  and not getattr(c, "is_full", False)]
    if not openstaand:
        return None
    datums = {_deadline_van(c) for c in openstaand}
    return datums.pop() if len(datums) == 1 else None


def registration_state(activity: Activity, *, component=None,
                       today: Optional[date] = None) -> RegistrationState:
    """The one place that decides whether an activity takes a new registration.

    Until #974 two places decided that, each in its own way. The registration route
    refused when no date lay in the future; the public card decided separately
    whether to show the button. Adding a deadline to both would have been the
    duplication `CLAUDE.md` warns about — so both ask this function instead.

    **The deadline is inclusive and Belgian.** `registration_closes_on` is the last
    day a registration is accepted, until midnight in Brussels. `today` defaults to
    `belgian_today()` and not to `date.today()`, because the container may run on
    UTC and a deadline would then close two hours late in summer.

    **The deadline belongs to the COMPONENT since #1053.** Pass the component
    where one is known — the registration route and the modal both know it — and
    this function answers for that component. Without one it answers for the
    activity as a whole: closed only when every component has a deadline that has
    passed, because as long as one component still takes registrations, the
    activity is not closed. The barbecue closing a week early may not close
    cornhole; that is the case this moved for.

    **Only for NEW registrations.** A board member correcting an existing
    registration after the deadline — or refunding one on a cancelled activity — is
    fixing a record, not letting someone in.
    Call this where a registration is created, and nowhere a registration is merely
    changed.
    """
    from app.kernel.clock import belgian_today

    vandaag = today or belgian_today()
    # Cancelled first: for whoever reads the refusal, "this activity was cancelled"
    # is the true reason even when its dates have also passed.
    if activity.is_cancelled:
        return RegistrationState.CANCELLED
    if not any(_effective_end(d) >= vandaag for d in activity.dates):
        return RegistrationState.PAST
    if component is not None:
        deadline = _deadline_van(component)
        if deadline is not None and vandaag > deadline:
            return RegistrationState.CLOSED
        return RegistrationState.OPEN
    onderdelen = list(activity.sub_registrations)
    if onderdelen and all((d := _deadline_van(c)) is not None and vandaag > d
                          for c in onderdelen):
        return RegistrationState.CLOSED
    return RegistrationState.OPEN


# The status label an activity shows, per registration state (#977).
#
# Until #977 the router worked this label out on its own — past, cancelled or open
# — next to `registration_state`, which since #974 decides exactly that with a
# reason. Two places deciding "open" is how the deadline would have been missing
# from the label: a card read "Open" next to "Inschrijvingen afgesloten". The label
# is now a lookup on the state, so a new reason to close appears here or fails the
# test that walks every state.
#
# "Afgesloten" for a passed deadline was decided by Koen on 16 September 2026: an
# activity that no longer takes registrations is not "open", even though it has not
# taken place yet.
STATUS_LABELS: dict["RegistrationState", str] = {
    RegistrationState.OPEN: "Open",
    RegistrationState.CLOSED: "Afgesloten",
    RegistrationState.PAST: "Voorbij",
    RegistrationState.CANCELLED: "Geannuleerd",
}


def status_label(activity: Activity, *, today: Optional[date] = None) -> str:
    """The label for this activity, derived from `registration_state`."""
    return STATUS_LABELS[registration_state(activity, today=today)]


def registration_refusal(activity: Activity, *, component=None,
                         today: Optional[date] = None) -> Optional[str]:
    """Why a new registration is refused, in the words the visitor reads — or None.

    Next to `registration_state` and not inside the route, because two callers show
    this text: the registration route when a form is posted, and the modal when it
    is opened. Two copies of the wording would drift the first time one is edited.
    """
    from app.i18n import _, long_date

    toestand = registration_state(activity, component=component, today=today)
    if toestand is RegistrationState.CANCELLED:
        return _("Deze activiteit is geannuleerd; inschrijven kan niet meer.")
    if toestand is RegistrationState.CLOSED:
        # De datum die de bezoeker leest, is die van ZIJN onderdeel (#1053) — met
        # verschillende datums per onderdeel zou elke andere datum liegen.
        if component is not None:
            return (_("De inschrijvingen voor dit onderdeel zijn afgesloten sinds "
                      "%(datum)s.")
                    % {"datum": long_date(_deadline_van(component))})
        # Zonder onderdeel gaat het over de activiteit als geheel, en die is pas
        # dicht als élk onderdeel dicht is — dus telt de LAATSTE datum.
        alle = open_deadlines(activity)
        return (_("De inschrijvingen zijn afgesloten sinds %(datum)s.")
                % {"datum": long_date(alle[-1] if alle else None)})
    if toestand is RegistrationState.PAST:
        return _("Activity is no longer open for registration")
    return None


class ActivityOption(NamedTuple):
    """Eén regel in een activiteiten-keuzelijst."""

    id: int
    name: str
    first_date: Optional[date]


def _rollback_on_rule_violation(db):
    """A rejected write leaves no half transaction behind (#792).

    The coherence rule of a date row fires during the flush, and the session is then in
    "pending rollback": everything done with that session afterwards fails with an
    incomprehensible error instead of with the reason. For `create_activity` that is
    not theoretical either — the activity itself has already been flushed by then.

    The rule violation itself travels on to the caller; only the transaction is
    cleaned up.
    """
    from contextlib import contextmanager

    @contextmanager
    def _guard():
        try:
            yield
        except ActiviteitFout:
            db.rollback()
            raise

    return _guard()


def slugify(naam: str) -> str:
    """Een vriendelijke URL uit een naam (#884): kleine letters, cijfers, koppeltekens.

    Alleen een VOORSTEL. Wat er daarna met de slug gebeurt, beslist de bestuurder — deze
    functie wordt nooit opnieuw over een bestaande activiteit gehaald, want dan zou de
    slug de naam volgen en zouden gedeelde links breken bij een hernoeming.
    """
    import re
    import unicodedata

    kaal = unicodedata.normalize("NFKD", naam or "").encode("ascii", "ignore").decode()
    kaal = re.sub(r"[^a-zA-Z0-9]+", "-", kaal).strip("-").lower()
    return re.sub(r"-{2,}", "-", kaal)[:255]


def slug_is_vrij(db, slug: str, *, behalve_id: int | None = None) -> bool:
    """Is deze slug nog vrij binnen de actieve tenant? (#884)

    De globale tenant-filter doet hier het werk: dezelfde slug bij twee verschillende
    afdelingen is toegestaan, want dat zijn andere verenigingen op andere adressen.
    """
    query = db.query(Activity).filter(Activity.slug == slug)
    if behalve_id is not None:
        query = query.filter(Activity.id != behalve_id)
    return query.first() is None


def activity_by_key(db, key: str):
    """Een activiteit op id ÓF op slug (#884).

    De nummer-URL blijft werken, en dat is geen hoffelijkheid: er staan nummer-URL's in
    verstuurde e-mails, in WhatsApp-berichten en in de zoekmachine. Alleen cijfers = een
    id; al de rest = een slug.
    """
    sleutel = (key or "").strip()
    if not sleutel:
        return None
    if sleutel.isdigit():
        return db.query(Activity).filter(Activity.id == int(sleutel)).first()
    return db.query(Activity).filter(Activity.slug == sleutel.lower()).first()


def _controleer_slug(db, slug: str | None, *, behalve_id: int | None = None) -> str | None:
    """Normaliseer en controleer een ingetypte slug; None blijft None (optioneel)."""
    if slug is None:
        return None
    schoon = slugify(slug)
    if not schoon:
        return None
    if not slug_is_vrij(db, schoon, behalve_id=behalve_id):
        from app.i18n import _ as vertaal

        # Zichtbaar weigeren en niet stil een cijfer erachter zetten: dan krijgt de
        # bestuurder een adres dat hij niet gekozen heeft en nergens ziet.
        raise ActiviteitFout(vertaal(
            "De URL '%(slug)s' is al in gebruik door een andere activiteit."
        ) % {"slug": schoon})
    return schoon


def create_activity(db, *, name: str, location=None, poster_url=None, description=None,
                    members_only: bool = False, dates=(), actor=None,
                    slug: str | None = None) -> Activity:
    """Maak een activiteit met haar eerste datums (#679, batch 1).

    De audit-snapshots horen bij de mutatie, niet bij de route: een activiteit die
    buiten de JSON-router om wordt aangemaakt, hoort dezelfde geschiedenis te
    krijgen. `dates` bevat objecten met start_date/end_date/start_time/end_time —
    de Pydantic-vorm van de router past daarop, maar de service eist ze niet.
    """
    from app.domains.audit.api import snapshot_activity, snapshot_activity_date

    # #884: bij het AANMAKEN een voorstel uit de naam, tenzij er één meegegeven is.
    # Botst het voorstel, dan blijft de slug leeg in plaats van te falen: de activiteit
    # aanmaken is de handeling, niet het kiezen van een adres — dat kan daarna in de
    # editor, met een zichtbare melding als het nog steeds botst.
    if slug is None:
        voorstel = slugify(name)
        slug = voorstel if voorstel and slug_is_vrij(db, voorstel) else None
    else:
        slug = _controleer_slug(db, slug)
    activity = Activity(name=name, location=location, poster_url=poster_url,
                        description=description,
                        members_only=bool(members_only), slug=slug)
    db.add(activity)
    db.flush()
    snapshot_activity(db, activity, operation="insert", action="activity_created",
                      source="admin_manual", actor=actor)

    with _rollback_on_rule_violation(db):
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
    # #884: een slug volgt de naam NIET. Hij verandert alleen wanneer hij expliciet in
    # `velden` staat — en dan met een zichtbare controle op botsing. Zou hij meebewegen
    # met de naam, dan sterft elke gedeelde link bij een hernoeming, zonder dat iemand
    # het merkt: wie op zo'n link klikt is geen bestuurder.
    if "slug" in velden:
        velden = {**velden,
                  "slug": _controleer_slug(db, velden["slug"], behalve_id=activity_id)}
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
    with _rollback_on_rule_violation(db):
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
    with _rollback_on_rule_violation(db):
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


# ActiviteitFout lived here until #792 and now lives in models.py: the first rule that
# sits on the object itself (`ActivityDate.validate_coherence`) needs the type, and a
# model may not import from the service. It is imported at the top, so
# `service.ActiviteitFout` keeps working — the same class, not a second one.
#
# Why it exists: not an HTTPException, because that belongs to the entrance and not to
# the rule. Without this type the rule "free and pay-on-site cannot both hold" would
# stay in the route, and then it would not apply to anyone calling the service directly.


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
        registration_closes_on=gegevens.registration_closes_on,
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
        is_active=gegevens.is_active,
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


def publicly_bookable_products(component) -> list:
    """The products a visitor may pick on the public registration form (#1191).

    One source for everything the form derives from its product list: the rows it
    renders, the quantity it opens with, the opening total. Reading
    `component.products` a second time next to this is how the rows and the total
    drift apart — the duplication rule in CLAUDE.md, applied to one screen.

    An inactive product is left out here and refused by `check_publicly_bookable`;
    the back office keeps seeing all of them on purpose.
    """
    return [p for p in (component.products or []) if p.is_active]


def check_publicly_bookable(activity, product_ids) -> None:
    """Refuse a PUBLIC registration on an inactive product (#1191).

    In the service layer and not in the template. `_inschrijf_form.html` leaves an
    inactive product out, but that is form and not meaning: POST
    /activities/{id}/register is an entrance of its own and accepted every product
    of the activity, exactly the mistake #733 corrected for the mandatory fields.

    Deliberately NOT applied to the back office. `add_order_line` may book an
    inactive product, because that is the whole point of the flag: the board puts a
    guest list on a product no visitor may pick. The separation is **structural** —
    two entrances, two rules — and not an origin argument that a caller can forget.
    A future shared helper taking `origin="public"|"admin"` would put the public
    path one missing argument away from accepting an inactive product again.

    Only what is actually booked counts: an item with quantity 0 creates no line,
    so it is not a booking and not refused.
    """
    from app.i18n import _ as vertaal

    # Derived from `publicly_bookable_products` instead of carrying its own
    # `is_active` filter: a gate that keeps its own copy of what it guards ends up
    # guarding the copy. With `not p.is_active` written out here, the form could
    # hide a product this check still accepts, or the other way round — and both
    # read as green.
    boekbaar = {p.id for comp in activity.sub_registrations
                for p in publicly_bookable_products(comp)}
    if any(product_id not in boekbaar for product_id in product_ids):
        raise ActiviteitFout(vertaal(
            "Dit product is niet beschikbaar om online in te schrijven."))


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


def _ontbreekt(waarde) -> bool:
    """Leeg of enkel witruimte telt als niet ingevuld.

    Dezelfde normalisatie als hieronder, en bewust vóór die stap: `strip() or None`
    maakt van "   " een NULL, dus ná de normalisatie is een leeg veld niet meer van
    een weggelaten veld te onderscheiden.
    """
    return not (str(waarde) if waarde is not None else "").strip()


def controleer_inschrijfvelden(component, *, contact_name, phone, team_name) -> None:
    """De verplichte velden van een inschrijving (#733).

    Het publieke formulier belóófde vier verplichte velden en de server dwong er
    één af (`EmailStr`). `required` in HTML is vorm, geen betekenis: het geldt alleen
    voor wie het formulier in een browser invult, en `POST /activities/{id}/register`
    kwam er zonder mobiel nummer of ploegnaam gewoon door.

    Hier en niet in de router, want de regel moet gelden op élke weg: het publieke
    scherm, de JSON-API en het beheerscherm dat achteraf corrigeert.

    De ploegnaam hangt aan de HUIDIGE configuratie van het onderdeel, niet aan de
    geschiedenis van de rij: vraagt het onderdeel er een, dan hoort ze er te zijn —
    ook bij een oude inschrijving die er nog geen had (Koens keuze, 8 sep 2026). Een
    regel die aan de geschiedenis hangt is niet uit te leggen en niet te toetsen.
    """
    from app.i18n import _ as vertaal

    if _ontbreekt(contact_name):
        raise ActiviteitFout(vertaal("Vul een naam in."))
    if _ontbreekt(phone):
        raise ActiviteitFout(vertaal("Vul een mobiel nummer in."))
    if getattr(component, "team_name_required", False) and _ontbreekt(team_name):
        raise ActiviteitFout(vertaal("Dit onderdeel vraagt een ploegnaam."))


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
    # #733: toetsen op de UITKOMST, niet op wat er meegestuurd is. Het beheerscherm
    # stuurt alle velden mee, maar de oude #283-aanroep alleen `remarks` — dan telt
    # wat er al staat. Vóór de mutatie, zodat een weigering niets wegschrijft.
    onderdeel = (db.query(ActivitySubRegistration)
                 .filter(ActivitySubRegistration.id == reg.component_id).first()
                 if reg.component_id else None)
    controleer_inschrijfvelden(
        onderdeel,
        **{veld: gezet.get(veld, getattr(reg, veld))
           for veld in ("contact_name", "phone", "team_name")})
    gewijzigd = False
    for veld in ("contact_name", "contact_email", "phone", "team_name", "remarks"):
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


def record_kop_ctx(db, activiteit, viewer_email: str, actief: str, *,
                   reg_count: int | None = None) -> dict:
    """Alles wat `_aa_recordkop.html` nodig heeft, op één plek (#1070).

    Die kop wordt door VIER sjablonen ingesloten — Overzicht, de paginaschil, de
    tab Inschrijvingen en de tab Betalingen — en de context werd op twee plaatsen
    met de hand samengesteld: in `activities.admin_ui` en in `payment.ui`. Zolang
    het bij twee sleutels bleef viel dat niet op; #1070 voegt er een derde toe, en
    dan is het de duplicatie uit `CLAUDE.md`: de ene plek loopt achter en het
    sjabloon faalt onder `StrictUndefined` — geen leeg vlak, een fout.

    De knop naar de Design Studio draagt **altijd hetzelfde label** en laat de
    BESTEMMING het aantal volgen (Koen, 20 september 2026): geen ontwerp → er een
    maken, precies één → dat ontwerp, meerdere → de lijst van deze activiteit.
    De keuze valt hier en niet in het sjabloon, zoals de laaggate vraagt.
    """
    from app.config import settings
    from app.domains.designstudio.api import designs_for_activity
    from app.kernel.tenant_config import tenant_admin_chat_enabled

    ontwerpen = designs_for_activity(db, activiteit.id)
    if not ontwerpen:
        designs_href = f"/admin/ontwerpen/nieuw?activity_id={activiteit.id}"
    elif len(ontwerpen) == 1:
        designs_href = f"/admin/ontwerpen/{ontwerpen[0].id}"
    else:
        designs_href = f"/admin/ontwerpen?activity_id={activiteit.id}"
    return {
        "record_tabs": record_tabs(db, activiteit, viewer_email, actief,
                                   reg_count=reg_count),
        # Golf 10 (#913): de "AI · Activiteit"-knop bestaat alleen als Raakje voor
        # beheer aan staat — één bron (kernel, CR-07 §6.3), geen eigen vlag ernaast.
        "raakje_admin": tenant_admin_chat_enabled(db),
        # #1075: the overlay carries the same microphone as every other Raakje,
        # and the button needs to know which speech path to take — read from the
        # configuration here, the same value the reporting Raakje passes on.
        "stt_mode": settings.stt_mode,
        "designs_href": designs_href,
    }


def record_tabs(db, activiteit, viewer_email: str, actief: str, *,
                reg_count: int | None = None) -> list[dict]:
    """De tabbalk van de activiteit-recordpagina (golf 8, #913) — P13 in
    tabvorm: elke tab een bestaand lijstscherm in de scope van dit record.

    Betalingen alleen voor wie ze mag zien (#544: +FINANCE) — een tab die op
    een 403 uitkomt is erger dan geen tab; sinds Koens feedbackronde wijst hij
    naar de INGEBEDDE pagina onder het record. Lokale imports: auth en payment
    importeren zelf uit activities.
    """
    from app.i18n import _
    from app.domains.auth.api import may_view_payments
    from app.domains.payment.api import count_registration_records_by_activity

    if reg_count is None:
        reg_count = registration_count_for(db, activiteit.id)
    tabs = [
        {"label": _("Overzicht"),
         "href": f"/admin/activiteiten/{activiteit.id}",
         "active": actief == "overzicht"},
        {"label": _("Inschrijvingen") + f" {reg_count}",
         "href": f"/admin/activiteiten/{activiteit.id}/inschrijvingen",
         "active": actief == "inschrijvingen"},
    ]
    if may_view_payments(db, viewer_email):
        n = count_registration_records_by_activity(db, activiteit.id)
        tabs.append({"label": _("Betalingen") + f" {n}",
                     "href": f"/admin/activiteiten/{activiteit.id}/betalingen",
                     "active": actief == "betalingen"})
    return tabs


INSCHRIJVING_SORT_VELDEN = ("datum", "naam")


def sorteer_inschrijvingen(regs, sort: str, richting: str):
    """Whitelist-sortering van verrijkte inschrijvingsrijen — één bron voor de
    Inschrijvingen-tab van activiteit én gezin (Koens unificatievraag, 15 sep).
    Geeft (rijen, sort, richting) terug met gevalideerde waarden; #761-tiebreaker
    op id zodat gelijke sleutels een stabiele volgorde houden."""
    sleutels = {
        "datum": lambda r: (r["registered_at"] is None,
                            str(r["registered_at"] or "")),
        "naam": lambda r: ((r["contact_name"] or "") == "",
                           str(r["contact_name"] or "").lower()),
    }
    if sort not in sleutels:
        sort = "datum"
    richting = "desc" if richting == "desc" else "asc"
    sleutel = sleutels[sort]
    return (sorted(regs, key=lambda r: (*sleutel(r), r["id"]),
                   reverse=richting == "desc"), sort, richting)


def inschrijving_tabs(db, registration_id: int, viewer_email: str,
                      actief: str, *, terug: str = "") -> list[dict]:
    """Tabbalk van de inschrijvings-recordpagina (feedback 15 sep): Overzicht ·
    Betalingen N — zelfde patroon als activiteit en gezin; de P13-chip op dat
    scherm verdween hiermee. `terug` (door de route gevalideerd) reist met
    beide tabs mee, zodat de A7-terugweg een tabwissel overleeft."""
    from urllib.parse import quote

    from app.i18n import _
    from app.domains.auth.api import may_view_payments
    from app.domains.payment.api import get_records_for

    suffix = f"?terug={quote(terug, safe='')}" if terug else ""
    tabs = [{"label": _("Overzicht"),
             "href": f"/admin/inschrijvingen/{registration_id}{suffix}",
             "active": actief == "overzicht"}]
    if may_view_payments(db, viewer_email):
        n = len(get_records_for(db, "registration", registration_id))
        tabs.append({"label": _("Betalingen") + f" {n}",
                     "href": (f"/admin/inschrijvingen/{registration_id}"
                              f"/betalingen{suffix}"),
                     "active": actief == "betalingen"})
    return tabs


def inschrijving_kop_ctx(db, registration_id: int, viewer_email: str,
                         actief: str, terug: str = "") -> dict | None:
    """Context van `_insch_recordkop.html`, op één plek: de Overzicht-pagina en
    de ingebedde Betalingen-tab renderen dezelfde kop — naam, contextregel,
    A7-terugweg (incl. labelafleiding uit het gevalideerde pad) en tabs.
    None wanneer de inschrijving niet bestaat."""
    from app.i18n import _
    from app.ui import veilige_terug

    reg = get_registration(db, registration_id, include_deleted=True)
    if reg is None:
        return None
    activity = db.get(Activity, reg.activity_id)
    component = (next((c for c in activity.sub_registrations
                       if c.id == reg.component_id), None)
                 if activity is not None else None)
    titel = activity.name if activity is not None else ""
    pad = veilige_terug(terug, f"/admin/activiteiten/{reg.activity_id}")
    # P3: het label wordt uit het gevalideerde pad afgeleid, nooit uit een
    # eigen parameter — een tweede vrije waarde zou een tweede te valideren
    # ding zijn.
    if pad.startswith("/admin/betalingen"):
        label = _("Betalingen")
    elif pad.startswith("/admin/activiteiten"):
        label = titel
    elif pad.startswith("/admin/leden"):
        label = _("Gezin")
    else:
        label = _("Terug")
    return {
        "activiteit_id": reg.activity_id,
        "activiteit_titel": titel,
        "component_naam": component.name if component is not None else None,
        "terug": pad, "terug_label": label,
        "record_tabs": inschrijving_tabs(db, registration_id, viewer_email,
                                         actief, terug=pad),
    }


def registration_contact_names(db) -> list[str]:
    """De contactnamen op inschrijvingen — vrije tekst, dus geen `Person` (#1135).

    De naadwachter scant elk uitgaand AI-bericht op namen uit de administratie, en
    die lijst kwam tot nu toe alleen uit `mdm.persons`. Een contactnaam staat hier,
    op de inschrijving zelf, en werd dus niet herkend.

    Hoe groot dat gat is, hangt van de data af en niet van deze functie: een
    contactnaam die toevallig gelijk is aan de naam van iemand in de
    ledenadministratie, was al gedekt. Wat hier bij komt zijn de namen van mensen
    die alleen als inschrijver bestaan — en op PROD is dat het gewone geval, want
    van 132 inschrijvingen dragen er 129 alleen een contactnaam.

    Soft-deleted inschrijvingen tellen niet mee: hun naam staat nergens meer op een
    scherm, dus hij hoort ook niet in een blokkeerlijst.
    """
    rijen = (db.query(Registration.contact_name)
             .filter(Registration.deleted_at.is_(None),
                     Registration.contact_name.isnot(None),
                     Registration.contact_name != "")
             .all())
    return [rij[0] for rij in rijen]


def registration_count_for(db, activity_id: int) -> int:
    """Alleen het aantal (golf 8, #913) — één rij, hoe groot de lijst ook is;
    de query-budget-gate (#651) rekent in opgehaalde rijen."""
    from sqlalchemy import func as _func

    return db.query(_func.count(Registration.id)).filter(
        Registration.activity_id == activity_id).scalar() or 0


def registration_ids_for(db, activity_id: int) -> list[int]:
    """Alleen de ids van de inschrijvingen van één activiteit (golf 8, #913).

    Voor tellers en scopes: de recordpagina en de betalingen-activiteitscope
    hebben geen verrijking nodig, en de query-budget-gate (#651) bewaakt dat
    het detailscherm niet de hele boom ophaalt."""
    return [rij[0] for rij in
            db.query(Registration.id)
            .filter(Registration.activity_id == activity_id).all()]


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
        "component_name": component_name,
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
                      without_component: bool = False,
                      alle: bool = False) -> Optional[list[dict]]:
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
    # Golf 8 (#913): `alle` overstijgt de twee filters — de recordpagina toont
    # één lijst over alle onderdelen heen, mét Onderdeel-kolom.
    if alle:
        pass
    elif without_component:
        vraag = vraag.filter(Registration.component_id.is_(None))
    elif component_id is not None:
        vraag = vraag.filter(Registration.component_id == component_id)
    regs = (vraag
            .order_by(Registration.registered_at.asc(), Registration.id.asc())
            .all())
    return [enrich_registration(r, activity) for r in regs]


# ── What a meeting agenda needs (CR-09, #258) ────────────────────────────────
# An activity's window is min(start_date) .. max(end_date or start_date) over its
# date rows, so a run of dates counts as one span — the photo hunt runs from June
# to September and is one activity, not four.

class ActivitySpan(NamedTuple):
    """One activity with the window it occupies and how full it is."""

    activity: Activity
    start: date
    end: date
    registered: int
    capacity: Optional[int]


def _spans(db, having) -> list[ActivitySpan]:
    """Activities whose span matches `having`, chronologically.

    `having` receives the aggregated first/last columns so both callers express
    their window in the same vocabulary; the counting itself happens once, below.
    """
    first = func.min(ActivityDate.start_date)
    last = func.max(func.coalesce(ActivityDate.end_date, ActivityDate.start_date))
    rows = (db.query(Activity, first.label("first"), last.label("last"))
            .join(ActivityDate, ActivityDate.activity_id == Activity.id)
            .filter(Activity.is_cancelled.is_(False))
            .group_by(Activity.id)
            .having(having(first, last))
            .order_by(first.asc(), Activity.id.asc())
            .all())
    counts = registration_counts(db, [a.id for a, _f, _l in rows])
    return [ActivitySpan(activity=a, start=f, end=l,
                         registered=counts.get(a.id, (0, None))[0],
                         capacity=counts.get(a.id, (0, None))[1])
            for a, f, l in rows]


def activities_active_between(db, start: date, end: date) -> list[ActivitySpan]:
    """Activities that were running or started in the window [start, end).

    What a meeting evaluates: everything since the previous meeting, a still
    running activity included — the photo hunt sat under evaluation every month
    while it ran, which is exactly what the board discussed.
    """
    return _spans(db, lambda first, last: (first < end) & (last >= start))


def activities_from(db, day: date) -> list[ActivitySpan]:
    """Activities starting on or after `day` — the whole planned programme.

    No time window (CR-09 §3.21): booking a venue a year ahead is a normal agenda
    point, and the secretary leaves off what has nothing to discuss.
    """
    return _spans(db, lambda first, last: first >= day)


def registration_counts(db, activity_ids: list[int]) -> dict[int, tuple[int, Optional[int]]]:
    """Per activity: registrations booked, and the capacity if one is set.

    The counting rule — the sum of the item quantities, or one per registration
    without items — is the same rule the full-check and the public occupancy use;
    it lives here once, and `_component_occupancy` in the router asks for the
    per-component grain of the same thing.

    Capacity is the sum of the component maxima, and `None` when no component
    caps: an activity without a maximum shows "N ingeschreven", never "N/0".
    """
    if not activity_ids:
        return {}
    per_component = _booked_per_component(db, activity_ids)
    caps = (db.query(ActivitySubRegistration.activity_id,
                     func.sum(ActivitySubRegistration.max_participants),
                     func.count(ActivitySubRegistration.max_participants))
            .filter(ActivitySubRegistration.activity_id.in_(activity_ids))
            .group_by(ActivitySubRegistration.activity_id)
            .all())
    capacity = {activity_id: (int(total) if capped else None)
                for activity_id, total, capped in caps}

    booked: dict[int, int] = {}
    component_owner = dict(
        db.query(ActivitySubRegistration.id, ActivitySubRegistration.activity_id)
        .filter(ActivitySubRegistration.activity_id.in_(activity_ids)).all())
    for component_id, quantity in per_component.items():
        activity_id = component_owner.get(component_id)
        if activity_id is not None:
            booked[activity_id] = booked.get(activity_id, 0) + quantity
    # Registrations that hang on no component still count as attendance.
    loose = (db.query(Registration.activity_id, func.count(Registration.id))
             .filter(Registration.activity_id.in_(activity_ids),
                     Registration.component_id.is_(None))
             .group_by(Registration.activity_id)
             .all())
    for activity_id, count in loose:
        booked[activity_id] = booked.get(activity_id, 0) + int(count or 0)

    return {activity_id: (booked.get(activity_id, 0), capacity.get(activity_id))
            for activity_id in activity_ids}


def _booked_per_component(db, activity_ids: list[int]) -> dict[int, int]:
    """Booked places per component: the sum of the item quantities, or one per
    registration without items. One batched query; the global soft-delete and
    tenant filters apply, so deleted registrations do not count."""
    from app.domains.activities.models import RegistrationItem

    if not activity_ids:
        return {}
    item_sum = (db.query(RegistrationItem.registration_id.label("rid"),
                         func.sum(RegistrationItem.quantity).label("q"))
                .group_by(RegistrationItem.registration_id)
                .subquery())
    rows = (db.query(Registration.component_id,
                     func.sum(func.coalesce(item_sum.c.q, 1)))
            .outerjoin(item_sum, item_sum.c.rid == Registration.id)
            .filter(Registration.activity_id.in_(activity_ids),
                    Registration.component_id.isnot(None))
            .group_by(Registration.component_id)
            .all())
    return {component_id: int(quantity or 0) for component_id, quantity in rows}


# Publieke naam (golf 8, #913): de recordpagina leest de bezetting via de
# facade; de router-doorgang blijft voor zijn vier bestaande aanroepers.
booked_per_component = _booked_per_component


# ── Organisatoren (#1004, CR-10 §3.9) ────────────────────────────────────────
#
# Up to three "trekkers" per activity. The limit lives in THREE places on
# purpose (CLAUDE.md, "Validation layers"): the screen hides the button (a
# courtesy), this service refuses the fourth with a readable message (the rule),
# and a CHECK on `sort_order` in the database is the net (migration 133).
#
# Who is pickable is a member: everyone in a household (Koen, 16 September
# 2026). The circle of a meeting is deliberately wider — see `search_persons`.

MAX_ORGANISERS = 3


class OrganiserView(NamedTuple):
    """One organiser as a poster (or a letter) reads it.

    `email` and `mobile` are what should be published: the override of this
    activity when it is filled, otherwise the person's own contact details. The
    caller does not have to know that difference exists.
    """

    id: int
    person_id: int
    name: str
    is_contact: bool
    email: str
    mobile: str
    email_override: str
    mobile_override: str
    #: #1032 — of dit gegeven op de affiche mag. `email`/`mobile` hierboven zijn
    #: al leeg wanneer het niet mag; deze twee zijn voor het SCHERM, dat de
    #: vinkjes moet kunnen tonen.
    show_email: bool
    show_mobile: bool
    sort_order: int


def _organiser_rows(db, activity_id: int):
    from app.domains.activities.models import ActivityOrganiser

    return (db.query(ActivityOrganiser)
            .filter(ActivityOrganiser.activity_id == activity_id)
            .order_by(ActivityOrganiser.sort_order, ActivityOrganiser.id).all())


def organisers_for(db, activity_id: int) -> list:
    """The organisers of one activity, in their own order (#1004)."""
    from app.domains.mdm.api import ContactDetail, Person

    rijen = _organiser_rows(db, activity_id)
    if not rijen:
        return []
    person_ids = [r.person_id for r in rijen]
    personen = {p.id: p for p in db.query(Person).filter(Person.id.in_(person_ids)).all()}
    contacten: dict[tuple[int, str | None], str] = {}
    for detail in (db.query(ContactDetail)
                   .filter(ContactDetail.person_id.in_(person_ids)).all()):
        # CR-12 phase 2: the `.upper()` was a normalisation because the column
        # accepted any spelling. The code list does that now; `code_of` returns
        # the code, whether it comes back as a member or as a bare code.
        sleutel = (detail.person_id, code_of(detail.contact_type_code))
        if detail.value and sleutel not in contacten:
            contacten[sleutel] = detail.value

    gezien = []
    for rij in rijen:
        person = personen.get(rij.person_id)
        naam = f"{person.first_name} {person.last_name}".strip() if person else ""
        # #1032: de volgorde is de regel. Eerst wint de override van de
        # ledenwaarde, en PAS DAARNA beslist de vlag of er iets naar buiten gaat.
        # Andersom zou een ingevulde override alsnog lekken terwijl het vinkje uit
        # staat — precies wat dit issue moet voorkomen.
        email = rij.email_override or contacten.get((rij.person_id, CONTACT.EMAIL), "")
        mobile = rij.mobile_override or contacten.get((rij.person_id, CONTACT.MOBILE), "")
        gezien.append(OrganiserView(
            id=rij.id, person_id=rij.person_id, name=naam,
            is_contact=bool(rij.is_contact),
            email=email if rij.show_email else "",
            mobile=mobile if rij.show_mobile else "",
            email_override=rij.email_override or "",
            mobile_override=rij.mobile_override or "",
            show_email=bool(rij.show_email),
            show_mobile=bool(rij.show_mobile),
            sort_order=rij.sort_order))
    return gezien


def board_notes(db, activity_id: int) -> str:
    """De interne bestuursnota van één activiteit (#1028), of "".

    Met `db.get` en niet met een query: de recordpagina heeft de rij vlak
    hiervoor al geladen, dus dit komt uit de identiteitskaart van de sessie en
    kost geen tweede query — gemeten met het querybudget (#645 D), dat er anders
    één bijkrijgt voor een veld dat al binnen was.

    Als losse functie en niet als veld op `ActivityResponse`: dat schema is óók
    het publieke JSON-antwoord, dus een veld erbij is een lek.
    """
    rij = db.get(Activity, activity_id)
    return (rij.board_notes if rij is not None else "") or ""


def add_organiser(db, activity_id: int, person_id: int):
    """Add one organiser. Refuses a fourth, and someone who is no member."""
    from app.domains.activities.models import ActivityOrganiser
    from app.domains.mdm.api import Person, is_member
    from app.i18n import _

    if db.query(Activity).filter(Activity.id == activity_id).first() is None:
        raise LookupError("Activiteit niet gevonden")
    rijen = _organiser_rows(db, activity_id)
    if len(rijen) >= MAX_ORGANISERS:
        raise ActiviteitFout(_(
            "Een activiteit heeft hoogstens %(n)s organisatoren.") % {"n": MAX_ORGANISERS})
    if any(r.person_id == person_id for r in rijen):
        raise ActiviteitFout(_("Die persoon staat er al bij."))
    person = db.query(Person).filter(Person.id == person_id).first()
    if person is None:
        raise LookupError("Persoon niet gevonden")
    if not is_member(db, person_id):
        # The rule, not the screen: the picker only SHOWS members, and a form
        # post does not go through the picker.
        raise ActiviteitFout(_("Alleen leden kunnen organisator zijn."))

    gebruikt = {r.sort_order for r in rijen}
    volgende = next(i for i in range(MAX_ORGANISERS) if i not in gebruikt)
    rij = ActivityOrganiser(activity_id=activity_id, person_id=person_id,
                            sort_order=volgende)
    db.add(rij)
    db.commit()
    db.refresh(rij)
    return rij


def update_organiser(db, activity_id: int, organiser_id: int, velden: dict):
    """The tick and the two overrides. An empty override means "the member's own"."""
    rij = next((r for r in _organiser_rows(db, activity_id) if r.id == organiser_id), None)
    if rij is None:
        raise LookupError("Organisator niet gevonden")
    for vlag in ("is_contact", "show_email", "show_mobile"):
        if vlag in velden:
            setattr(rij, vlag, bool(velden[vlag]))
    for veld in ("email_override", "mobile_override"):
        if veld in velden:
            waarde = (velden[veld] or "").strip()
            setattr(rij, veld, waarde or None)
    db.commit()
    db.refresh(rij)
    return rij


def remove_organiser(db, activity_id: int, organiser_id: int) -> bool:
    rij = next((r for r in _organiser_rows(db, activity_id) if r.id == organiser_id), None)
    if rij is None:
        return False
    db.delete(rij)
    db.commit()
    return True
