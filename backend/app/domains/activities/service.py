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

from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import date, timedelta
from typing import TYPE_CHECKING, Any, Callable, Iterable, Iterator, NamedTuple, Optional

from sqlalchemy import func, not_, nulls_last
from sqlalchemy.orm import Session

from app.domains.activities.codes import INDIVIDUAL
from app.domains.activities.models import (
    ActiviteitFout,
    Activity,
    ActivityDate,
    ActivitySubRegistration,
    Registration,
    RegistrationHistory,
    RegistrationState,
)
from app.domains.mdm.api import CONTACT
from app.kernel.codes import code_label, code_of

if TYPE_CHECKING:
    from app.domains.activities.models import ActivityOrganiser, ActivityProduct, RegistrationItem
    from app.schemas.activity import (
        ActivityDateCreate,
        ActivityDateResponse,
        ActivityResponse,
        ComponentCreate,
        ComponentResponse,
        ProductCreate,
        RegistrationCreate,
    )


def _effective_end(ad: ActivityDate | ActivityDateResponse) -> date:
    return ad.end_date or ad.start_date


def is_upcoming(activity_date: ActivityDate | ActivityDateResponse, today: date) -> bool:
    """Whether a date of an activity still lies ahead: its last day is today or later.

    The one place that says it (CR-13 phase 1): `registration_state` asks it for
    "has this activity passed", and the API's card asks it to sort a date into past
    or coming. The router had its own copy of this and of `_effective_end`.
    """
    return ends_on_or_after(_effective_end(activity_date), today)


def ends_on_or_after(last_day: Any, today: date) -> Any:
    """A date whose last day is today or later still lies ahead — the one comparison
    behind "has this passed" (CR-13 phase 4). It takes a `date` for one activity
    date and a column expression for a query, so the list's filters and
    `registration_state` cannot drift apart."""
    return last_day >= today


def date_upcoming(today: date) -> Any:
    """The SQL side: an `ActivityDate` that still lies ahead (for a query)."""
    return ends_on_or_after(func.coalesce(ActivityDate.end_date, ActivityDate.start_date), today)


def date_passed(today: date) -> Any:
    """The SQL side: an `ActivityDate` that has passed."""
    return not_(date_upcoming(today))


def _deadline_van(component: ActivitySubRegistration | ComponentResponse) -> Optional[date]:
    return getattr(component, "registration_closes_on", None)


def open_deadlines(activity: Activity) -> list[date]:
    """De uiterste inschrijfdatums van deze activiteit, zonder dubbels (#1053).

    Eén datum in de lijst betekent: elk onderdeel dat er een heeft, heeft
    dezelfde — dat is het gewone geval (76 van de 86 activiteiten met onderdelen
    op HDEV hebben er precies één). Meer dan één betekent dat de datum bij het
    onderdeel hoort en niet bovenaan de kaart.
    """
    return sorted(
        {d for d in (_deadline_van(c) for c in activity.sub_registrations) if d is not None}
    )


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


def card_deadline(
    activity: Activity | ActivityResponse, *, today: Optional[date] = None
) -> Optional[date]:
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
    openstaand = [
        c
        for c in activity.sub_registrations
        if registration_state(activity, component=c, today=today) is RegistrationState.OPEN
        and not getattr(c, "is_full", False)
    ]
    if not openstaand:
        return None
    datums = {_deadline_van(c) for c in openstaand}
    return datums.pop() if len(datums) == 1 else None


def registration_state(
    activity: Activity | ActivityResponse,
    *,
    component: ActivitySubRegistration | ComponentResponse | None = None,
    today: Optional[date] = None,
) -> RegistrationState:
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
    if not any(is_upcoming(d, vandaag) for d in activity.dates):
        return RegistrationState.PAST
    if component is not None:
        deadline = _deadline_van(component)
        if deadline is not None and vandaag > deadline:
            return RegistrationState.CLOSED
        return RegistrationState.OPEN
    onderdelen = list(activity.sub_registrations)
    if onderdelen and all((d := _deadline_van(c)) is not None and vandaag > d for c in onderdelen):
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
# taken place yet. Since CR-12 phase 4 the four words live in the label table of
# the DERIVED list `registration_state` (§B5.3 note 5): computed, never stored,
# and read with `code_label()` like every other code.


def status_label(activity: Activity, *, today: Optional[date] = None) -> str:
    """The label for this activity, derived from `registration_state`."""
    from app.domains.activities.codes import REGISTRATION_STATE

    return code_label(REGISTRATION_STATE.name, registration_state(activity, today=today))


def registration_refusal(
    activity: Activity,
    *,
    component: ActivitySubRegistration | ComponentResponse | None = None,
    today: Optional[date] = None,
) -> Optional[str]:
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
            return _("De inschrijvingen voor dit onderdeel zijn afgesloten sinds %(datum)s.") % {
                "datum": long_date(_deadline_van(component))
            }
        # Zonder onderdeel gaat het over de activiteit als geheel, en die is pas
        # dicht als élk onderdeel dicht is — dus telt de LAATSTE datum.
        alle = open_deadlines(activity)
        return _("De inschrijvingen zijn afgesloten sinds %(datum)s.") % {
            "datum": long_date(alle[-1] if alle else None)
        }
    if toestand is RegistrationState.PAST:
        return _("Activity is no longer open for registration")
    return None


class ActivityOption(NamedTuple):
    """Eén regel in een activiteiten-keuzelijst."""

    id: int
    name: str
    first_date: Optional[date]


def _rollback_on_rule_violation(db: Session) -> AbstractContextManager[None]:
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
    def _guard() -> Iterator[None]:
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


def slug_is_vrij(db: Session, slug: str, *, behalve_id: int | None = None) -> bool:
    """Is deze slug nog vrij binnen de actieve tenant? (#884)

    De globale tenant-filter doet hier het werk: dezelfde slug bij twee verschillende
    afdelingen is toegestaan, want dat zijn andere verenigingen op andere adressen.
    """
    query = db.query(Activity).filter(Activity.slug == slug)
    if behalve_id is not None:
        query = query.filter(Activity.id != behalve_id)
    return query.first() is None


def activity_by_key(db: Session, key: str) -> Activity | None:
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


def _controleer_slug(db: Session, slug: str | None, *, behalve_id: int | None = None) -> str | None:
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
        raise ActiviteitFout(
            vertaal("De URL '%(slug)s' is al in gebruik door een andere activiteit.")
            % {"slug": schoon}
        )
    return schoon


def create_activity(
    db: Session,
    *,
    name: str,
    location: str | None = None,
    poster_url: str | None = None,
    description: str | None = None,
    members_only: bool = False,
    dates: Iterable[ActivityDateCreate] = (),
    actor: str | None = None,
    slug: str | None = None,
) -> Activity:
    """Maak een activiteit met haar eerste datums (#679, batch 1).

    De audit-snapshots horen bij de mutatie, niet bij de route: een activiteit die
    buiten de JSON-router om wordt aangemaakt, hoort dezelfde geschiedenis te
    krijgen. `dates` bevat objecten met start_date/end_date/start_time/end_time —
    de Pydantic-vorm van de router past daarop, maar de service eist ze niet.
    """
    activity = _add_activity(
        db,
        name=name,
        location=location,
        poster_url=poster_url,
        description=description,
        members_only=members_only,
        dates=dates,
        actor=actor,
        slug=slug,
        action="activity_created",
    )
    with _rollback_on_rule_violation(db):
        db.commit()
    return activity


def _add_activity(
    db: Session,
    *,
    name: str,
    location: str | None,
    poster_url: str | None,
    description: str | None,
    members_only: bool,
    dates: Iterable[Any],
    actor: str | None,
    slug: str | None,
    action: str,
) -> Activity:
    """Add an activity and its dates, with their history, WITHOUT committing.

    `create_activity` commits right after; `copy_activity` (#1397) adds the
    organisers first, so the copy is one transaction. A rule violation on a date
    row rolls back here, as before.
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
    activity = Activity(
        name=name,
        location=location,
        poster_url=poster_url,
        description=description,
        members_only=bool(members_only),
        slug=slug,
    )
    db.add(activity)
    db.flush()
    snapshot_activity(
        db,
        activity,
        operation="insert",
        action=action,
        source="admin_manual",
        actor=actor,
    )

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
            snapshot_activity_date(
                db,
                ad,
                operation="insert",
                action=action,
                source="admin_manual",
                actor=actor,
            )
    return activity


class CopySuggestions(NamedTuple):
    """The two starting dates the copy step offers (#1397)."""

    same_weekday: date  # 52 weeks later: Bouwen, Saturday to Saturday
    same_date: date  # the same calendar date a year later: Kerstherberg, 25 December


def copy_suggestions(first: date) -> CopySuggestions:
    """Same weekday 52 weeks later, and the same calendar date a year later.

    29 February has no twin in a common year; it becomes 28 February.
    """
    try:
        same_date = first.replace(year=first.year + 1)
    except ValueError:
        same_date = first.replace(year=first.year + 1, day=28)
    return CopySuggestions(same_weekday=first + timedelta(weeks=52), same_date=same_date)


def first_date_of(activity: Activity) -> date | None:
    """The earliest start date of an activity, the one a copy is moved by."""
    return min((d.start_date for d in activity.dates), default=None)


def organisers_left_out_of_a_copy(db: Session, activity: Activity) -> list[ActivityOrganiser]:
    """The organisers a copy would not take along: no longer a member (#1397).

    `add_organiser` refuses someone who is no member, and a copy is no way
    around that rule. The copy step shows these before anything is made.
    """
    from app.domains.mdm.api import is_member

    return [o for o in activity.organisers if not is_member(db, o.person_id)]


def copy_activity(
    db: Session, activity_id: int, *, first_date: date | None, actor: str | None = None
) -> Activity | None:
    """Copy an activity to a new date, in one transaction (#1397).

    Comes along: every field of the activity, its dates moved by one difference
    in days (the new first date minus the old one; hours stay), and its
    organisers who are still members. Not: components and products (the board
    sets those up months ahead, with that year's prices), registrations,
    payments, history, and the poster (open question for Koen).

    The copy is on the public agenda at once, without a way to register until
    a component is added. Its slug is suggested from the name, as for a new
    activity; the original keeps that address, so the copy usually starts
    without one. Returns None when the activity does not exist.
    """
    from types import SimpleNamespace

    from app.domains.activities.models import ActivityOrganiser

    source = _activity_met_boom(db, activity_id)
    if source is None:
        return None
    first = first_date_of(source)
    if first is not None and first_date is None:
        from app.i18n import _

        # The rule, not the screen: every date moves by the difference from the
        # first, so a copy of an activity with dates needs that new first date.
        raise ActiviteitFout(_("Kies de nieuwe begindatum."))
    shift = (first_date - first) if (first and first_date) else timedelta(0)
    left_out = {o.id for o in organisers_left_out_of_a_copy(db, source)}
    # One transaction: everything below lands, or nothing does. A savepoint and
    # not `db.rollback()`: a failure undoes the copy and only the copy, whatever
    # the caller's session already holds. The explicit form and not `with`, as in
    # `register`: the context-manager form refuses a transaction begun inside it.
    savepoint = db.begin_nested()
    try:
        copy = _add_activity(
            db,
            name=source.name,
            location=source.location,
            poster_url=None,
            description=source.description,
            members_only=source.members_only,
            dates=[
                SimpleNamespace(
                    start_date=d.start_date + shift,
                    end_date=d.end_date + shift if d.end_date else None,
                    start_time=d.start_time,
                    end_time=d.end_time,
                )
                for d in sorted(source.dates, key=lambda d: (d.start_date, d.id))
            ],
            actor=actor,
            slug=None,
            action="activity_copied",
        )
        copy.board_notes = source.board_notes
        for organiser in source.organisers:
            if organiser.id in left_out:
                continue
            db.add(
                ActivityOrganiser(
                    activity_id=copy.id,
                    person_id=organiser.person_id,
                    sort_order=organiser.sort_order,
                    is_contact=organiser.is_contact,
                    email_override=organiser.email_override,
                    mobile_override=organiser.mobile_override,
                    show_email=organiser.show_email,
                    show_mobile=organiser.show_mobile,
                )
            )
        db.flush()
        from app.kernel.contracts.activities import ActivityCopied
        from app.kernel.events import publish

        # The poster design is another domain's: it hears the fact, in this
        # transaction, and copies its own (Koen, 30 September 2026).
        publish(
            ActivityCopied(source_activity_id=source.id, copy_activity_id=copy.id, actor=actor),
            db,
        )
    except Exception:
        savepoint.rollback()
        raise
    db.commit()
    return copy


def update_activity(
    db: Session, activity_id: int, velden: dict, *, actor: str | None = None
) -> Optional[Activity]:
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
        velden = {**velden, "slug": _controleer_slug(db, velden["slug"], behalve_id=activity_id)}
    for veld, waarde in velden.items():
        setattr(activity, veld, waarde)
    snapshot_activity(
        db,
        activity,
        operation="update",
        action="activity_updated",
        source="admin_manual",
        actor=actor,
    )
    db.commit()
    db.refresh(activity)
    return activity


def delete_activity(db: Session, activity_id: int, *, actor: str | None = None) -> bool:
    """Soft delete van de hele boom (#166). Geeft False als ze niet bestaat.

    Datums, onderdelen, producten, inschrijvingen en bestelregels gaan mee.
    Betalingen NIET: die zijn een financieel feit en blijven bestaan — dat is
    dezelfde regel die #667 met een gate vastlegde.
    """
    from app.domains.audit.api import (
        snapshot_activity,
        snapshot_activity_date,
        snapshot_component,
        snapshot_product,
    )
    from app.soft_delete import soft_delete

    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if activity is None:
        return False
    for d in activity.dates:
        snapshot_activity_date(
            db, d, operation="delete", action="activity_deleted", source="admin_manual", actor=actor
        )
        soft_delete(d)
    for comp in activity.sub_registrations:
        for p in comp.products:
            snapshot_product(
                db,
                p,
                operation="delete",
                action="activity_deleted",
                source="admin_manual",
                actor=actor,
            )
            soft_delete(p)
        snapshot_component(
            db,
            comp,
            operation="delete",
            action="activity_deleted",
            source="admin_manual",
            actor=actor,
        )
        soft_delete(comp)
    for reg in activity.registrations:
        for item in reg.items:
            soft_delete(item)
        soft_delete(reg)
    snapshot_activity(
        db,
        activity,
        operation="delete",
        action="activity_deleted",
        source="admin_manual",
        actor=actor,
    )
    soft_delete(activity)
    db.commit()
    return True


def add_activity_date(
    db: Session, activity_id: int, gegevens: ActivityDateCreate, *, actor: str | None = None
) -> Optional[ActivityDate]:
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
        snapshot_activity_date(
            db, ad, operation="insert", action="date_created", source="admin_manual", actor=actor
        )
        db.commit()
    db.refresh(ad)
    return ad


def update_activity_date(
    db: Session, activity_id: int, date_id: int, velden: dict, *, actor: str | None = None
) -> Optional[ActivityDate]:
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
        snapshot_activity_date(
            db, ad, operation="update", action="date_updated", source="admin_manual", actor=actor
        )
        db.commit()
    db.refresh(ad)
    return ad


def delete_activity_date(
    db: Session, activity_id: int, date_id: int, *, actor: str | None = None
) -> bool:
    """Soft delete van één datum. False als ze niet bij deze activiteit hoort."""
    from app.domains.audit.api import snapshot_activity_date
    from app.soft_delete import soft_delete

    ad = _datum(db, activity_id, date_id)
    if ad is None:
        return False
    snapshot_activity_date(
        db, ad, operation="delete", action="date_deleted", source="admin_manual", actor=actor
    )
    soft_delete(ad)
    db.commit()
    return True


def _datum(db: Session, activity_id: int, date_id: int) -> Optional[ActivityDate]:
    return (
        db.query(ActivityDate)
        .filter(ActivityDate.id == date_id, ActivityDate.activity_id == activity_id)
        .first()
    )


# ActiviteitFout lived here until #792 and now lives in models.py: the first rule that
# sits on the object itself (`ActivityDate.validate_coherence`) needs the type, and a
# model may not import from the service. It is imported at the top, so
# `service.ActiviteitFout` keeps working — the same class, not a second one.
#
# Why it exists: not an HTTPException, because that belongs to the entrance and not to
# the rule. Without this type the rule "free and pay-on-site cannot both hold" would
# stay in the route, and then it would not apply to anyone calling the service directly.


def add_component(
    db: Session, activity_id: int, gegevens: ComponentCreate, *, actor: str | None = None
) -> ActivitySubRegistration | None:
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
        registration_type_code=INDIVIDUAL,
        price=0,
        is_free=True,
    )
    db.add(component)
    db.flush()
    snapshot_component(
        db,
        component,
        operation="insert",
        action="component_created",
        source="admin_manual",
        actor=actor,
    )
    db.commit()
    db.refresh(component)
    return component


def update_component(
    db: Session, activity_id: int, component_id: int, velden: dict, *, actor: str | None = None
) -> ActivitySubRegistration | None:
    """Werk een onderdeel bij. None als het niet bij deze activiteit hoort."""
    from app.domains.audit.api import snapshot_component

    component = get_component(db, component_id, activity_id=activity_id)
    if component is None:
        return None
    if "form_id" in velden:
        _check_questions(db, component, velden["form_id"])
    for veld, waarde in velden.items():
        setattr(component, veld, waarde)
    snapshot_component(
        db,
        component,
        operation="update",
        action="component_updated",
        source="admin_manual",
        actor=actor,
    )
    db.commit()
    db.refresh(component)
    return component


def _check_questions(db: Session, component: ActivitySubRegistration, form_id: int | None) -> None:
    """May this component ask the questions of `form_id` (None: none)? CR-14 §B4.5.

    Detaching is always allowed — the answers stay with their registrations. A
    form must be one a registration page can ask (`forms.api.attach_refusal`, F2).
    Replacing the form is refused once a registration has answered (F13): the
    answers of one component belong to one form, and the export has one set of
    columns."""
    from app.domains.forms.api import attach_refusal, get_form
    from app.i18n import _ as vertaal

    if form_id is None or form_id == component.form_id:
        return
    try:
        form = get_form(db, form_id)
    except LookupError:
        raise ActiviteitFout(vertaal("Dat formulier bestaat niet.")) from None
    refusal = attach_refusal(form)
    if refusal:
        raise ActiviteitFout(refusal)
    if component.form_id is not None and (
        db.query(Registration.id)
        .filter(
            Registration.component_id == component.id,
            Registration.form_submission_id.isnot(None),
        )
        .first()
        is not None
    ):
        raise ActiviteitFout(
            vertaal(
                "Dit onderdeel heeft al antwoorden op zijn vragen. Een ander formulier "
                "koppelen kan niet; ontkoppel het en maak een nieuw onderdeel voor de "
                "nieuwe vragen."
            )
        )


def question_forms(db: Session, activity_id: int) -> tuple[list[tuple[int, str]], dict]:
    """What the component settings offer under "Extra vragen": the forms that can be
    attached, by title, plus a form a component already asks that can no longer be
    offered (closed since) — otherwise the select would silently drop it on save.
    And {component id: form id} for the components that ask questions."""
    from app.domains.forms.api import attachable_forms, get_form

    chosen = {
        c.id: c.form_id
        for c in db.query(ActivitySubRegistration)
        .filter(
            ActivitySubRegistration.activity_id == activity_id,
            ActivitySubRegistration.form_id.isnot(None),
        )
        .all()
    }
    options = [(f.id, f.title) for f in attachable_forms(db)]
    offered = {i for i, _t in options}
    for form_id in sorted(set(chosen.values()) - offered):
        try:
            options.append((form_id, get_form(db, form_id).title))
        except LookupError:
            # Deleted in the builder since (a soft reference, #396): not offered,
            # so saving the component detaches it.
            continue
    return options, chosen


def delete_component(
    db: Session, activity_id: int, component_id: int, *, actor: str | None = None
) -> bool:
    """Soft delete van een onderdeel én zijn producten. False als het niet bestaat."""
    from app.domains.audit.api import snapshot_component, snapshot_product
    from app.soft_delete import soft_delete

    component = get_component(db, component_id, activity_id=activity_id)
    if component is None:
        return False
    for p in component.products:
        snapshot_product(
            db,
            p,
            operation="delete",
            action="component_deleted",
            source="admin_manual",
            actor=actor,
        )
        soft_delete(p)
    snapshot_component(
        db,
        component,
        operation="delete",
        action="component_deleted",
        source="admin_manual",
        actor=actor,
    )
    soft_delete(component)
    db.commit()
    return True


def _controleer_afrekening(is_free: bool | None, pay_on_site: bool | None) -> None:
    """Gratis én ter plaatse te betalen sluiten elkaar uit.

    Een domeinregel, dus hier en niet in de route: ze geldt voor élke ingang.
    """
    if is_free and pay_on_site:
        from app.i18n import _ as vertaal

        raise ActiviteitFout(
            vertaal("Een product kan niet tegelijk gratis én ter plaatse te betalen zijn.")
        )


def add_product(
    db: Session,
    activity_id: int,
    component_id: int,
    gegevens: ProductCreate,
    *,
    actor: str | None = None,
) -> ActivityProduct | None:
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
    snapshot_product(
        db,
        product,
        operation="insert",
        action="product_created",
        source="admin_manual",
        actor=actor,
    )
    db.commit()
    db.refresh(product)
    return product


def update_product(
    db: Session, component_id: int, product_id: int, velden: dict, *, actor: str | None = None
) -> ActivityProduct | None:
    """Werk een product bij. None als het niet bij dit onderdeel hoort."""
    from app.domains.audit.api import snapshot_product

    product = _product(db, component_id, product_id)
    if product is None:
        return None
    for veld, waarde in velden.items():
        setattr(product, veld, waarde)
    # Ná het toepassen: de combinatie kan ook ontstaan door één veld te wijzigen.
    _controleer_afrekening(product.is_free, product.pay_on_site)
    snapshot_product(
        db,
        product,
        operation="update",
        action="product_updated",
        source="admin_manual",
        actor=actor,
    )
    db.commit()
    db.refresh(product)
    return product


def delete_product(
    db: Session, component_id: int, product_id: int, *, actor: str | None = None
) -> bool:
    """Soft delete van één product. False als het niet bij dit onderdeel hoort."""
    from app.domains.audit.api import snapshot_product
    from app.soft_delete import soft_delete

    product = _product(db, component_id, product_id)
    if product is None:
        return False
    snapshot_product(
        db,
        product,
        operation="delete",
        action="product_deleted",
        source="admin_manual",
        actor=actor,
    )
    soft_delete(product)
    db.commit()
    return True


def _product(db: Session, component_id: int, product_id: int) -> ActivityProduct | None:
    from app.domains.activities.models import ActivityProduct

    return (
        db.query(ActivityProduct)
        .filter(ActivityProduct.id == product_id, ActivityProduct.component_id == component_id)
        .first()
    )


# ── Bestelregels en inschrijvingen (#679, batch 4) ────────────────────────────


def _registratie(db: Session, activity_id: int, registration_id: int) -> Registration | None:
    return (
        db.query(Registration)
        .filter(Registration.id == registration_id, Registration.activity_id == activity_id)
        .first()
    )


def _regel(db: Session, registration_id: int, item_id: int) -> RegistrationItem | None:
    from app.domains.activities.models import RegistrationItem

    return (
        db.query(RegistrationItem)
        .filter(RegistrationItem.id == item_id, RegistrationItem.registration_id == registration_id)
        .first()
    )


def publicly_bookable_products(component: ActivitySubRegistration) -> list:
    """The products a visitor may pick on the public registration form (#1191).

    One source for everything the form derives from its product list: the rows it
    renders, the quantity it opens with, the opening total. Reading
    `component.products` a second time next to this is how the rows and the total
    drift apart — the duplication rule in CLAUDE.md, applied to one screen.

    An inactive product is left out here and refused by `check_publicly_bookable`;
    the back office keeps seeing all of them on purpose.
    """
    return [p for p in (component.products or []) if p.is_active]


def check_publicly_bookable(activity: Activity, product_ids: Iterable[int]) -> None:
    """Refuse a PUBLIC registration on an inactive product (#1191).

    In the service layer and not in the template. The registration page leaves an
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
    boekbaar = {
        p.id for comp in activity.sub_registrations for p in publicly_bookable_products(comp)
    }
    if any(product_id not in boekbaar for product_id in product_ids):
        raise ActiviteitFout(vertaal("Dit product is niet beschikbaar om online in te schrijven."))


def controleer_bestelproduct(
    db: Session, activity_id: int, registration: Registration, product_id: int
) -> ActivityProduct | None:
    """Een bestelregel mag enkel een product van deze activiteit/dit onderdeel dragen.

    Domeinregel, dus hier: ze beschermt de koppeling tussen inschrijving en
    aanbod, en die moet gelden ongeacht welke ingang een regel toevoegt. Geeft het
    product terug; `ActiviteitFout` als de koppeling niet klopt, None als het
    product niet bestaat — twee verschillende dingen, dus twee verschillende
    antwoorden.
    """
    from app.domains.activities.models import ActivityProduct
    from app.i18n import _ as vertaal

    product = db.query(ActivityProduct).filter(ActivityProduct.id == product_id).first()
    if product is None:
        return None
    comp = get_component(db, product.component_id)
    if comp is None or comp.activity_id != activity_id:
        raise ActiviteitFout(vertaal("Product hoort niet bij deze activiteit."))
    if registration.component_id is not None and product.component_id != registration.component_id:
        raise ActiviteitFout(vertaal("Product hoort niet bij het onderdeel van deze inschrijving."))
    return product


def add_order_line(
    db: Session,
    activity_id: int,
    registration_id: int,
    product_id: int,
    quantity: int,
    *,
    actor: str | None = None,
) -> Registration | None:
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

    bestaand = (
        db.query(RegistrationItem)
        .filter(
            RegistrationItem.registration_id == reg.id, RegistrationItem.product_id == product_id
        )
        .first()
    )
    if bestaand is not None:
        # #197: geen tweede regel voor hetzelfde product, maar optellen.
        bestaand.quantity += quantity
        db.flush()
        snapshot_registration_item(
            db,
            bestaand,
            operation="update",
            action="order_changed",
            source="admin_manual",
            actor=actor,
        )
    else:
        item = RegistrationItem(registration_id=reg.id, product_id=product_id, quantity=quantity)
        db.add(item)
        db.flush()
        snapshot_registration_item(
            db, item, operation="insert", action="order_changed", source="admin_manual", actor=actor
        )
    db.commit()
    _herbereken(db, reg, actor)
    return reg


def update_order_line(
    db: Session,
    activity_id: int,
    registration_id: int,
    item_id: int,
    *,
    product_id: int | None = None,
    quantity: int | None = None,
    actor: str | None = None,
) -> Registration | None:
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
            raise ActiviteitFout(
                vertaal("Aantal moet minstens 1 zijn; verwijder de regel om ze te schrappen.")
            )
        item.quantity = quantity
    db.flush()
    snapshot_registration_item(
        db, item, operation="update", action="order_changed", source="admin_manual", actor=actor
    )
    db.commit()
    _herbereken(db, reg, actor)
    return reg


def delete_order_line(
    db: Session, activity_id: int, registration_id: int, item_id: int, *, actor: str | None = None
) -> Registration | None:
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
    snapshot_registration_item(
        db, item, operation="delete", action="order_changed", source="admin_manual", actor=actor
    )
    soft_delete(item)
    db.commit()
    _herbereken(db, reg, actor)
    return reg


def _herbereken(db: Session, reg: Registration, actor: Optional[str]) -> None:
    """De betaalposten volgen de bestelling (#185) — through an event since CR-13
    phase 1, and in ONE transaction.

    Until phase 1 this called `payment.api.reconcile_registration_charges` itself and
    committed; now it publishes `OrderChanged` and payment's handler reconciles on the
    same session, before the one commit. A reconciliation that fails rolls the order
    change back: the line no longer stays changed with a balance that did not follow.
    """
    _order_changed(db, reg, actor)
    db.commit()
    db.refresh(reg)


def _order_changed(db: Session, reg: Registration, actor: Optional[str]) -> None:
    """Publish `OrderChanged` with the total its owner computes (§B4.9).

    Refuses to publish when nothing listens: an order change nobody reconciles is
    the #185 trap, and silence would make it invisible.
    """
    from app.domains.activities.totals import compute_registration_total
    from app.kernel.contracts.activities import OrderChanged
    from app.kernel.events import has_subscribers, publish

    if not has_subscribers(OrderChanged):
        raise RuntimeError(
            "OrderChanged has no subscriber — payment's handlers are not registered; "
            "an order change would leave the balance behind (#185)"
        )
    db.flush()
    db.refresh(reg)
    total, _lines = compute_registration_total(reg)
    publish(OrderChanged(registration_id=reg.id, total_due=str(total), actor=actor), db)


def register(
    db: Session,
    activity: Activity,
    data: "RegistrationCreate",
    *,
    person_id: int | None,
    actor: str,
    backoffice_products: bool = False,
) -> Registration:
    """Register somebody for an activity: every rule, then the rows (CR-13 phase 1).

    Until phase 1 these rules stood in `router.create_registration`, a door; now the
    door calls this and turns a refusal into its HTTP answer, and any other way in
    meets the same rules. In the order they were checked before, so a request that
    breaks two of them gets the same answer as before:

    1. the activity or the component is closed or cancelled (`registration_refusal`);
    2. the tenant's limit per e-mail address and component (`RegistrationLimitReached`);
    3. every product belongs to the activity, every quantity within the tenant's bounds;
    4. a public registration books only publicly bookable products (#1191);
    5. the registration's own rules — name and e-mail address as it is built, the
       mobile number at this entrance, the team name in `check()`;
    6. the component is not full.

    Adds the registration and its order lines, each line audited (#84, #713), and
    flushes. It does not commit: the door does, once, with the payment record and
    everything else of the request (§B4.1).
    """
    from app.domains.activities.models import (
        RegistrationItem,
        RegistrationLimitReached,
        RegistrationRefused,
    )
    from app.domains.audit.api import snapshot_registration_item
    from app.i18n import _ as vertaal
    from app.kernel.tenant_config import (
        tenant_max_item_quantity,
        tenant_max_registrations_per_email,
    )

    component = next((c for c in activity.sub_registrations if c.id == data.component_id), None)
    refusal = registration_refusal(activity, component=component)
    if refusal:
        raise RegistrationRefused(refusal)

    if data.contact_email:
        existing = (
            db.query(Registration)
            .filter(
                Registration.activity_id == activity.id,
                Registration.component_id == data.component_id,
                func.lower(Registration.contact_email) == data.contact_email.lower(),
            )
            .count()
        )
        limit = tenant_max_registrations_per_email(db)
        if existing >= limit:
            raise RegistrationLimitReached(
                vertaal(
                    "Er zijn al %(max)s inschrijvingen met dit "
                    "e-mailadres voor dit onderdeel. Neem contact op met het bestuur als je er meer nodig hebt."
                )
                % {"max": limit}
            )

    valid_product_ids = {p.id for c in activity.sub_registrations for p in c.products}
    max_quantity = tenant_max_item_quantity(db)
    for item in data.items:
        if item.product_id not in valid_product_ids:
            raise RegistrationRefused(vertaal("Ongeldig product in de inschrijving."))
        if item.quantity < 0 or item.quantity > max_quantity:
            raise RegistrationRefused(
                vertaal("Ongeldig aantal: kies een waarde tussen 0 en %(max)s.")
                % {"max": max_quantity}
            )

    if not backoffice_products:
        try:
            check_publicly_bookable(activity, [i.product_id for i in data.items if i.quantity > 0])
        except RegistrationRefused:
            raise
        except ActiviteitFout as refusal_of_product:
            raise RegistrationRefused(str(refusal_of_product)) from None

    registration = Registration(
        activity_id=activity.id,
        component_id=data.component_id,
        registration_type=INDIVIDUAL,
        contact_name=data.contact_name,
        contact_email=data.contact_email,
        phone=data.phone,
        team_name=data.team_name,
        payment_method=data.payment_method,
        remarks=data.remarks,
        person_id=person_id,
    )
    require_phone(data.phone)
    registration.component = component
    registration.check()

    new_quantity = sum(i.quantity for i in data.items) if data.items else 1
    if component is not None and component.max_participants is not None:
        taken = sum(
            (sum(it.quantity for it in reg.items) if reg.items else 1)
            for reg in activity.registrations
            if reg.component_id == data.component_id
        )
        if taken + new_quantity > component.max_participants:
            raise RegistrationRefused(
                vertaal("Dit onderdeel is volzet. Inschrijven is niet meer mogelijk.")
            )

    if component is not None and component.form_id is not None:
        # CR-14 F3: a component with questions asks for remarks itself if it wants
        # them; the registration's own remarks box is not shown, and stays empty.
        registration.remarks = None

    # CR-14 §B4.2: the answers come last, after every other rule, so nobody is
    # asked to fix an answer on a component that is full. A refused answer comes
    # after the rows are flushed — the savepoint takes them back with it.
    savepoint = db.begin_nested()
    try:
        db.add(registration)
        db.flush()
        for item in data.items:
            if item.quantity <= 0:
                continue
            line = RegistrationItem(
                registration_id=registration.id, product_id=item.product_id, quantity=item.quantity
            )
            db.add(line)
            db.flush()
            snapshot_registration_item(
                db,
                line,
                operation="insert",
                action="order_created",
                source="registration",
                actor=actor,
            )
        take_answers(db, registration, component, data.answers)
    except Exception:
        savepoint.rollback()
        raise
    savepoint.commit()
    db.flush()
    db.refresh(registration)
    return registration


def question_form(db: Session, component: Optional[ActivitySubRegistration]) -> Optional[Any]:
    """The form whose questions this component asks, or None (CR-14). An explicit
    read through `forms.api`, not an ORM relationship across the schema line
    (#396); a form deleted in the builder is None, and the component asks nothing."""
    if component is None or component.form_id is None:
        return None
    from app.domains.forms.api import find_form

    return find_form(db, component.form_id)


def registration_awaiting_answers(db: Session, token: str) -> Optional[Registration]:
    """The registration an answer link belongs to, while it still awaits its
    answers — or None (CR-14 §B4.8). The token is the only key: never the id. A
    used token is cleared, so it finds nothing, the same as a token that never
    existed (§B5: nothing revealed)."""
    if not token:
        return None
    registration = db.query(Registration).filter(Registration.answer_token == token).first()
    if registration is None or registration.component is None:
        return None
    if question_form(db, registration.component) is None:
        return None
    return registration


def edit_answers(
    db: Session, registration_id: int, answers: list, *, actor: Optional[str]
) -> Registration:
    """An organiser corrects a registration's answers (CR-14 §B4.7, R7).

    The same rules as when they were given — `forms.api.update_attached` runs
    `build_answers` again, so an empty required answer is refused here too, naming
    the question (`VeldFout`). In one transaction with one history row
    ("answers_edited") carrying each changed answer as "label: old → new"; a save
    that changes nothing writes no row. `LookupError` for an unknown registration;
    `ActiviteitFout` for one without answers to correct."""
    from app.domains.forms.api import submission_views, update_attached
    from app.i18n import _ as vertaal

    registration = db.query(Registration).filter(Registration.id == registration_id).first()
    if registration is None:
        raise LookupError("registration")
    submission_id = registration.form_submission_id
    if submission_id is None:
        raise ActiviteitFout(vertaal("Deze inschrijving heeft nog geen antwoorden."))
    before = dict(submission_views(db, [submission_id]).get(submission_id, []))
    savepoint = db.begin_nested()
    try:
        update_attached(db, submission_id, answers)
    except Exception:
        savepoint.rollback()
        raise
    savepoint.commit()
    after = submission_views(db, [submission_id]).get(submission_id, [])
    changes = [
        f"{label}: {before.get(label) or '—'} → {value or '—'}"
        for label, value in after
        if (before.get(label) or "") != (value or "")
    ]
    if changes:
        record_registration_history(
            db,
            registration,
            operation="update",
            action="answers_edited",
            source="admin_manual",
            actor=actor,
            answers="\n".join(changes),
        )
    db.commit()
    return registration


def answer_link_action(db: Session, registration: Registration) -> Optional[str]:
    """What the registration detail offers about the answer link (CR-14 §B4.8):
    "opnieuw" while the link is open, "sturen" for a registration without answers
    and without a link on a component that asks questions (the form was attached
    after it registered), None otherwise."""
    if registration.deleted_at is not None or registration.form_submission_id is not None:
        return None
    if registration.answer_token:
        return "opnieuw"
    return "sturen" if question_form(db, registration.component) is not None else None


def send_answer_link(db: Session, registration_id: int, *, actor: Optional[str]) -> Registration:
    """Send a registration its answer link, or send it again (CR-14 §B4.8).

    "Link sturen" creates the token for a registration that has none — the form was
    attached after it registered; "link opnieuw sturen" keeps the open one. Either
    way one history row ("answer_link_sent") and one mail, through `AnswerLinkSent`
    — a consequence in `mail`, so an event (CR-13 §B4.9). It fills in nothing else.
    `LookupError` for an unknown registration; `ActiviteitFout` when there is
    nothing to ask."""
    from app.i18n import _ as vertaal
    from app.kernel.contracts.activities import AnswerLinkSent
    from app.kernel.events import publish

    registration = db.query(Registration).filter(Registration.id == registration_id).first()
    if registration is None:
        raise LookupError("registration")
    if answer_link_action(db, registration) is None:
        raise ActiviteitFout(
            vertaal("Voor deze inschrijving zijn er geen vragen meer te beantwoorden.")
        )
    if not registration.answer_token:
        registration.answer_token = new_answer_token()
    db.flush()
    record_registration_history(
        db,
        registration,
        operation="update",
        action="answer_link_sent",
        source="admin_manual",
        actor=actor,
    )
    publish(
        AnswerLinkSent(
            registration_id=registration.id,
            to_email=registration.contact_email,
            name=registration.contact_name,
        ),
        db,
    )
    db.commit()
    return registration


def answer_path(db: Session, registration_id: Optional[int]) -> Optional[str]:
    """Where a registration's open answer link points (CR-14 §B4.8), or None when it
    has none — the one spelling of the path, for the thank-you page and the mail."""
    if registration_id is None:
        return None
    token = db.query(Registration.answer_token).filter(Registration.id == registration_id).scalar()
    return f"/inschrijving/{token}/vragen" if token else None


def answer_questions(db: Session, token: str, answers: list) -> Registration:
    """The answers of a registration that chose "later" (CR-14 §B4.8).

    The same rules as "now" (`take_answers`: the form's own, complete or refused),
    in one transaction with clearing the link: answered once, then the link is
    spent. The registration's closing date is not looked at — closing stops new
    registrations, not the answers of a household already registered (Q27).
    `LookupError` for an unknown or spent link."""
    registration = registration_awaiting_answers(db, token)
    if registration is None:
        raise LookupError("answer link")
    savepoint = db.begin_nested()
    try:
        registration.answer_token = None
        take_answers(db, registration, registration.component, answers)
    except Exception:
        savepoint.rollback()
        raise
    savepoint.commit()
    db.commit()
    return registration


def registration_answers(db: Session, registration: Registration) -> tuple[list, Optional[Any]]:
    """What the registration detail shows about the questions (CR-14 §B4.4): the
    answers as (label, value) in the form's order — or, while the link is still
    open, the moment they were asked (the registration's own date). Admin only:
    never on the public list (§B5)."""
    if registration.form_submission_id is not None:
        from app.domains.forms.api import submission_views

        rows = submission_views(db, [registration.form_submission_id])
        return rows.get(registration.form_submission_id, []), None
    if registration.answer_token:
        return [], registration.registered_at
    return [], None


def component_book(db: Session, activity: Activity, component: ActivitySubRegistration) -> list:
    """The book of a component (CR-14 §B1.1 F14): one block per living
    registration, by contact name — the name, the address of the person when the
    registration has one, the products, and the answers in the form's order (None
    while they are still to come). The same read as the export (`component_answers`),
    so the book and the sheet cannot say different things."""
    from app.domains.activities.export import component_answers

    registrations = sorted(
        (r for r in activity.registrations if r.component_id == component.id),
        key=lambda r: ((r.contact_name or "").lower(), r.id),
    )
    questions, answers = component_answers(db, component, registrations)
    book = []
    for reg in registrations:
        address = getattr(reg.person, "address", None) if reg.person is not None else None
        line = None
        if address is not None:
            street = " ".join(p for p in (address.street, address.house_number) if p)
            if address.bus_number:
                street += f" bus {address.bus_number}"
            place = (
                f"{address.postal_code.postal_code} {address.postal_code.municipality}"
                if address.postal_code is not None
                else ""
            )
            line = ", ".join(p for p in (street, place) if p)
        book.append(
            {
                "naam": reg.contact_name or "—",
                "adres": line,
                "producten": [
                    (item.quantity, item.product.name if item.product else "—")
                    for item in reg.items
                ],
                "antwoorden": (
                    list(zip(questions, answers[reg.id])) if reg.id in answers else None
                ),
            }
        )
    return book


def new_answer_token() -> str:
    """The secret of an "answer later" link: 32 random url-safe bytes, like the form
    builder's edit link (CR-14 §B5)."""
    import secrets

    return secrets.token_urlsafe(32)


def take_answers(
    db: Session,
    registration: Registration,
    component: Optional[ActivitySubRegistration],
    answers: Optional[list],
) -> None:
    """The answers to the component's questions, now or later (CR-14 §B4.2, §B4.8).

    A list — even an empty one — is "now": the form's own rules judge it
    (`forms.api.submit_attached`: required, ranges, options), and a refusal names
    the question (`VeldFout`, a 422 with the field). None is "later": the
    registration gets an answer link instead. Complete or not at all — no channel
    is lenient, and none stores half a form.
    """
    from app.i18n import _ as vertaal

    # Not `form_id`: a soft reference (#396) — a form deleted in the builder leaves
    # the id behind, and then the component asks nothing.
    form = question_form(db, component)
    if form is None:
        if answers:
            raise ActiviteitFout(vertaal("Dit onderdeel stelt geen vragen."))
        return
    if answers is None:
        registration.answer_token = new_answer_token()
        db.flush()
        return

    from app.domains.forms.api import submit_attached

    known = {f.id for f in form.fields}
    if any(a.field_id not in known for a in answers):
        raise ActiviteitFout(vertaal("Een antwoord hoort niet bij de vragen van dit onderdeel."))
    submission = submit_attached(
        db,
        form,
        answers,
        submitter_name=registration.contact_name,
        submitter_email=registration.contact_email,
    )
    registration.form_submission_id = submission.id
    db.flush()


def require_phone(phone: Optional[str]) -> None:
    """A registration needs a mobile number — at the entrances (#733, AC1).

    No database constraint on the registration phone (Koen, 29 September 2026);
    the entrances still require it: a new registration always (`register`, for the
    public form, the JSON API and the board's form), and the screen that corrects
    a registration when the number changes — a registration stored without one
    stays editable, a number cannot be cleared. Not a `@validates` on the
    row: a rule on one field without its constraint is what the *validator without
    constraint* gate refuses.
    """
    from app.domains.activities.models import _blank
    from app.i18n import _ as vertaal

    if _blank(phone):
        raise ActiviteitFout(vertaal("Vul een mobiel nummer in."))


def record_registration_history(
    db: Session,
    registration: Registration,
    *,
    operation: str,
    action: str,
    source: str,
    actor: Optional[str] = None,
    answers: Optional[str] = None,
) -> None:
    """One row in the registration's own history (#624): its contact details as
    they are now — append-only, so the previous row is the "old" value and this
    the new; `audit.changes` reads the pair into its "old → new" line.

    Moved here from `audit.service.snapshot_registration` in CR-14 phase 3: the
    table is this component's, and a foreign writer was what both CR-13 ratchets
    listed (§B4.9, "the audit snapshots move with their writers"). The same row, the
    same columns — `test_registration_history_row` was green before the move.
    `answers`: the registration's answers as label: value lines, where an action
    concerns them (CR-14 §B4.7)."""
    db.add(
        RegistrationHistory(
            registration_id=registration.id,
            contact_name=registration.contact_name,
            contact_email=registration.contact_email,
            phone=registration.phone,
            remarks=registration.remarks,
            answers=answers,
            operation=operation,
            action=action,
            source=source,
            actor=actor,
        )
    )


def update_registration_contact(
    db: Session,
    activity_id: int,
    registration_id: int,
    gezet: dict[str, Optional[str]],
    *,
    actor: Optional[str] = None,
) -> Optional[Registration]:
    """Corrigeer contactgegevens en/of opmerking (#283, uitgebreid #624).

    Raakt bestelregels, saldo en OGM NIET aan — dit is geen geldwijziging. Leeg of
    enkel witruimte wordt NULL. Enkel meegestuurde velden veranderen, zodat de
    oude #283-aanroep (alleen `remarks`) blijft werken.

    Alleen bij een échte wijziging een snapshot: een opslag zonder verschil hoort
    geen rij in het logboek op te leveren, anders wordt de geschiedenis ruis.
    """
    reg = _registratie(db, activity_id, registration_id)
    if reg is None:
        return None
    # #733, CR-13 phase 1: the registration says no itself — a blank name or e-mail
    # address on assignment, a missing team name when the flush runs its `check()`,
    # which reads the component loaded here; the mobile number is the entrance's.
    reg.component  # noqa: B018 — load it, so `check()` reads and never queries
    # The mobile number when it CHANGES, before anything changes: a registration
    # stored without one stays editable without adding one, a number cannot be
    # cleared (Koen, 29 September 2026). A new registration always needs one
    # (`register`).
    if "phone" in gezet:
        nieuw = (str(gezet["phone"]) if gezet["phone"] is not None else "").strip() or None
        if nieuw != reg.phone:
            require_phone(nieuw)
    gewijzigd = False
    try:
        for veld in ("contact_name", "contact_email", "phone", "team_name", "remarks"):
            if veld not in gezet:
                continue
            waarde = (str(gezet[veld]) if gezet[veld] is not None else "").strip() or None
            if getattr(reg, veld) != waarde:
                setattr(reg, veld, waarde)
                gewijzigd = True
        if gewijzigd:
            db.flush()
    except ActiviteitFout:
        # A refusal writes nothing, as it did when the rule ran before the mutation:
        # forget the assignments, so the screen that shows the refusal shows what is
        # stored and no later flush tries them again.
        db.expire(reg)
        raise
    if gewijzigd:
        record_registration_history(
            db,
            reg,
            operation="update",
            action="registration_contact_updated",
            source="admin_manual",
            actor=actor,
        )
    db.commit()
    db.refresh(reg)
    return reg


def delete_registration(
    db: Session, activity_id: int, registration_id: int, *, actor: Optional[str] = None
) -> bool:
    """Soft delete van een inschrijving én haar bestelregels (#313).

    Raakt de betaling NIET aan: een PaymentRecord is een financieel feit en blijft
    bestaan én zichtbaar (de verrijking haalt soft-deleted inschrijvingen op via
    include_deleted, #190). De bestelregels gaan wél mee, met snapshot, zodat ze
    niet in aantal- en saldoberekeningen lekken (#194).

    Het reconciliëren gebeurt vóór het schrappen van de inschrijving zelf: het
    besteltotaal is dan 0, dus een reeds betaald bedrag wordt een
    terugbetaalverplichting en een onbetaalde charge verdwijnt (#185/#313) — through
    `OrderChanged` since CR-13 phase 1, in the one transaction.
    """
    from app.domains.audit.api import snapshot_registration_item
    from app.soft_delete import soft_delete

    reg = _registratie(db, activity_id, registration_id)
    if reg is None:
        return False
    for item in list(reg.items):
        if getattr(item, "deleted_at", None) is None:
            snapshot_registration_item(
                db,
                item,
                operation="delete",
                action="order_changed",
                source="admin_manual",
                actor=actor,
            )
            soft_delete(item)
    # CR-13 phase 1: one transaction. The lines are gone (flushed, not committed),
    # the order total is therefore 0, payment reconciles on the event, and only then
    # the registration goes and everything commits — once. A failing reconciliation
    # rolls the lines back instead of leaving them deleted with a wrong balance.
    _order_changed(db, reg, actor)
    soft_delete(reg)
    db.commit()
    return True


# ── Export (#679, batch 5) ────────────────────────────────────────────────────


def component_export(db: Session, activity_id: int, component_id: int) -> tuple[bytes, str] | None:
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


def _activity_met_boom(db: Session, activity_id: int) -> Optional[Activity]:
    """Eén activiteit met haar datums, onderdelen en producten in één keer."""
    from sqlalchemy.orm import selectinload

    return (
        db.query(Activity)
        .options(
            selectinload(Activity.dates),
            selectinload(Activity.sub_registrations).selectinload(ActivitySubRegistration.products),
        )
        .filter(Activity.id == activity_id)
        .first()
    )


def get_activity(
    db: Session, activity_id: int, include_deleted: bool = False
) -> Optional[Activity]:
    query = db.query(Activity)
    if include_deleted:
        query = query.execution_options(include_deleted=True)
    return query.filter(Activity.id == activity_id).first()


def get_component(
    db: Session, component_id: int, activity_id: Optional[int] = None
) -> Optional[ActivitySubRegistration]:
    """Een onderdeel, eventueel binnen één activiteit.

    Met `activity_id` erbij is dit meteen de controle dat het onderdeel écht bij
    die activiteit hoort — anders zou /activiteiten/1/inschrijven/99 het onderdeel
    van een andere activiteit tonen.
    """
    query = db.query(ActivitySubRegistration).filter(ActivitySubRegistration.id == component_id)
    if activity_id is not None:
        query = query.filter(ActivitySubRegistration.activity_id == activity_id)
    return query.first()


def get_registration(
    db: Session, registration_id: int, include_deleted: bool = False
) -> Optional[Registration]:
    """Een inschrijving. Met `include_deleted` ook een geschrapte.

    Dat laatste is nodig op het betalingenscherm: een betaling is een financieel
    feit, dus de bewaarde naam moet zichtbaar blijven ook als de inschrijving
    geschrapt is (#190)."""
    query = db.query(Registration)
    if include_deleted:
        query = query.execution_options(include_deleted=True)
    return query.filter(Registration.id == registration_id).first()


def activity_options(db: Session) -> list[ActivityOption]:
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
    rijen = (
        db.query(Activity.id, Activity.name, func.min(ActivityDate.start_date))
        .outerjoin(ActivityDate, ActivityDate.activity_id == Activity.id)
        .group_by(Activity.id, Activity.name)
        .order_by(nulls_last(func.min(ActivityDate.start_date).desc()), Activity.name)
        .all()
    )
    return [ActivityOption(id=rij[0], name=rij[1], first_date=rij[2]) for rij in rijen]


def registrations_without_component_count(db: Session, activity_id: int) -> int:
    """Inschrijvingen op deze activiteit die aan geen enkel onderdeel hangen (#650).

    `Registration.component_id` is nullable met `ondelete="SET NULL"`: verwijder je
    een onderdeel, dan blijven de inschrijvingen bestaan, maar zonder onderdeel.
    Staat de knop "Toon inschrijvingen" enkel per onderdeel, dan zijn ze via geen
    enkele knop meer te bereiken — onzichtbaar terwijl ze in de databank staan.
    Dit getal bepaalt of het scherm daar een aparte kaart voor toont.

    De soft-delete- en tenantfilters komen van `with_loader_criteria`, dus een
    geschrapte inschrijving telt niet mee.
    """
    return (
        db.query(func.count(Registration.id))
        .filter(Registration.activity_id == activity_id, Registration.component_id.is_(None))
        .scalar()
        or 0
    )


def record_kop_ctx(
    db: Session,
    activiteit: Activity | ActivityResponse,
    viewer_email: str,
    actief: str,
    *,
    reg_count: int | None = None,
) -> dict:
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
        "record_tabs": record_tabs(db, activiteit, viewer_email, actief, reg_count=reg_count),
        # Golf 10 (#913): de "AI · Activiteit"-knop bestaat alleen als Raakje voor
        # beheer aan staat — één bron (kernel, CR-07 §6.3), geen eigen vlag ernaast.
        "raakje_admin": tenant_admin_chat_enabled(db),
        # #1075: the overlay carries the same microphone as every other Raakje,
        # and the button needs to know which speech path to take — read from the
        # configuration here, the same value the reporting Raakje passes on.
        "stt_mode": settings.stt_mode,
        "designs_href": designs_href,
    }


def record_tabs(
    db: Session,
    activiteit: Activity | ActivityResponse,
    viewer_email: str,
    actief: str,
    *,
    reg_count: int | None = None,
) -> list[dict]:
    """De tabbalk van de activiteit-recordpagina (golf 8, #913) — P13 in
    tabvorm: elke tab een bestaand lijstscherm in de scope van dit record.

    Betalingen alleen voor wie ze mag zien (#544: +FINANCE) — een tab die op
    een 403 uitkomt is erger dan geen tab; sinds Koens feedbackronde wijst hij
    naar de INGEBEDDE pagina onder het record. Lokale imports: auth en payment
    importeren zelf uit activities.
    """
    from app.domains.auth.api import may_view_payments
    from app.domains.payment.api import count_registration_records_by_activity
    from app.i18n import _

    if reg_count is None:
        reg_count = registration_count_for(db, activiteit.id)
    tabs = [
        {
            "label": _("Overzicht"),
            "href": f"/admin/activiteiten/{activiteit.id}",
            "active": actief == "overzicht",
        },
        {
            "label": _("Inschrijvingen") + f" {reg_count}",
            "href": f"/admin/activiteiten/{activiteit.id}/inschrijvingen",
            "active": actief == "inschrijvingen",
        },
    ]
    if may_view_payments(db, viewer_email):
        n = count_registration_records_by_activity(db, activiteit.id)
        tabs.append(
            {
                "label": _("Betalingen") + f" {n}",
                "href": f"/admin/activiteiten/{activiteit.id}/betalingen",
                "active": actief == "betalingen",
            }
        )
    return tabs


INSCHRIJVING_SORT_VELDEN = ("datum", "naam")


def sorteer_inschrijvingen(
    regs: list[dict], sort: str, richting: str
) -> tuple[list[dict], str, str]:
    """Whitelist-sortering van verrijkte inschrijvingsrijen — één bron voor de
    Inschrijvingen-tab van activiteit én gezin (Koens unificatievraag, 15 sep).
    Geeft (rijen, sort, richting) terug met gevalideerde waarden; #761-tiebreaker
    op id zodat gelijke sleutels een stabiele volgorde houden."""
    sleutels = {
        "datum": lambda r: (r["registered_at"] is None, str(r["registered_at"] or "")),
        "naam": lambda r: ((r["contact_name"] or "") == "", str(r["contact_name"] or "").lower()),
    }
    if sort not in sleutels:
        sort = "datum"
    richting = "desc" if richting == "desc" else "asc"
    sleutel = sleutels[sort]
    return (
        sorted(regs, key=lambda r: (*sleutel(r), r["id"]), reverse=richting == "desc"),
        sort,
        richting,
    )


def inschrijving_tabs(
    db: Session, registration_id: int, viewer_email: str, actief: str, *, terug: str = ""
) -> list[dict]:
    """Tabbalk van de inschrijvings-recordpagina (feedback 15 sep): Overzicht ·
    Betalingen N — zelfde patroon als activiteit en gezin; de P13-chip op dat
    scherm verdween hiermee. `terug` (door de route gevalideerd) reist met
    beide tabs mee, zodat de A7-terugweg een tabwissel overleeft."""
    from urllib.parse import quote

    from app.domains.auth.api import may_view_payments
    from app.domains.payment.api import get_records_for
    from app.i18n import _

    suffix = f"?terug={quote(terug, safe='')}" if terug else ""
    tabs = [
        {
            "label": _("Overzicht"),
            "href": f"/admin/inschrijvingen/{registration_id}{suffix}",
            "active": actief == "overzicht",
        }
    ]
    if may_view_payments(db, viewer_email):
        n = len(get_records_for(db, "registration", registration_id))
        tabs.append(
            {
                "label": _("Betalingen") + f" {n}",
                "href": (f"/admin/inschrijvingen/{registration_id}/betalingen{suffix}"),
                "active": actief == "betalingen",
            }
        )
    return tabs


def inschrijving_kop_ctx(
    db: Session, registration_id: int, viewer_email: str, actief: str, terug: str = ""
) -> dict | None:
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
    component = (
        next((c for c in activity.sub_registrations if c.id == reg.component_id), None)
        if activity is not None
        else None
    )
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
        "terug": pad,
        "terug_label": label,
        "record_tabs": inschrijving_tabs(db, registration_id, viewer_email, actief, terug=pad),
    }


def registration_contact_names(db: Session) -> list[str]:
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
    rijen = (
        db.query(Registration.contact_name)
        .filter(
            Registration.deleted_at.is_(None),
            Registration.contact_name.isnot(None),
            Registration.contact_name != "",
        )
        .all()
    )
    return [rij[0] for rij in rijen]


def registration_count_for(db: Session, activity_id: int) -> int:
    """Alleen het aantal (golf 8, #913) — één rij, hoe groot de lijst ook is;
    de query-budget-gate (#651) rekent in opgehaalde rijen."""
    from sqlalchemy import func as _func

    return (
        db.query(_func.count(Registration.id))
        .filter(Registration.activity_id == activity_id)
        .scalar()
        or 0
    )


def registration_ids_for(db: Session, activity_id: int) -> list[int]:
    """Alleen de ids van de inschrijvingen van één activiteit (golf 8, #913).

    Voor tellers en scopes: de recordpagina en de betalingen-activiteitscope
    hebben geen verrijking nodig, en de query-budget-gate (#651) bewaakt dat
    het detailscherm niet de hele boom ophaalt."""
    return [
        rij[0]
        for rij in db.query(Registration.id).filter(Registration.activity_id == activity_id).all()
    ]


def enrich_registration(reg: Registration, activity: Activity) -> dict:
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
        items.append(
            {
                "id": item.id,
                "product_id": item.product_id,
                "quantity": item.quantity,
                "product_name": pname,
                "component_name": cname or component_name,
            }
        )
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


def registrations_for(
    db: Session,
    activity_id: int,
    *,
    component_id: Optional[int] = None,
    without_component: bool = False,
    alle: bool = False,
) -> Optional[list[dict]]:
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
    regs = vraag.order_by(Registration.registered_at.asc(), Registration.id.asc()).all()
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


def _spans(db: Session, having: Callable[[Any, Any], Any]) -> list[ActivitySpan]:
    """Activities whose span matches `having`, chronologically.

    `having` receives the aggregated first/last columns so both callers express
    their window in the same vocabulary; the counting itself happens once, below.
    """
    first = func.min(ActivityDate.start_date)
    last = func.max(func.coalesce(ActivityDate.end_date, ActivityDate.start_date))
    rows = (
        db.query(Activity, first.label("first"), last.label("last"))
        .join(ActivityDate, ActivityDate.activity_id == Activity.id)
        .filter(Activity.is_cancelled.is_(False))
        .group_by(Activity.id)
        .having(having(first, last))
        .order_by(first.asc(), Activity.id.asc())
        .all()
    )
    counts = registration_counts(db, [a.id for a, _f, _l in rows])
    return [
        ActivitySpan(
            activity=a,
            start=first,
            end=last,
            registered=counts.get(a.id, (0, None))[0],
            capacity=counts.get(a.id, (0, None))[1],
        )
        for a, first, last in rows
    ]


def activities_active_between(db: Session, start: date, end: date) -> list[ActivitySpan]:
    """Activities that were running or started in the window [start, end).

    What a meeting evaluates: everything since the previous meeting, a still
    running activity included — the photo hunt sat under evaluation every month
    while it ran, which is exactly what the board discussed.
    """
    return _spans(db, lambda first, last: (first < end) & (last >= start))


def activities_from(db: Session, day: date) -> list[ActivitySpan]:
    """Activities starting on or after `day` — the whole planned programme.

    No time window (CR-09 §3.21): booking a venue a year ahead is a normal agenda
    point, and the secretary leaves off what has nothing to discuss.
    """
    return _spans(db, lambda first, last: first >= day)


class ActivityDateSpan(NamedTuple):
    """One date row of an activity — a single ride of a monthly ride (#1335).

    The grain a meeting point has since #1335: the board evaluates the last ride,
    not the activity, and discusses the guide of every coming ride separately.
    """

    activity: Activity
    row: ActivityDate
    start: date
    end: date


def _date_spans(db: Session, *conditions: Any) -> list[ActivityDateSpan]:
    """Date rows of activities that are not cancelled, chronologically."""
    last = func.coalesce(ActivityDate.end_date, ActivityDate.start_date)
    rows = (
        db.query(ActivityDate, Activity)
        .join(Activity, Activity.id == ActivityDate.activity_id)
        .filter(
            Activity.is_cancelled.is_(False),
            *[c(ActivityDate.start_date, last) for c in conditions],
        )
        .order_by(ActivityDate.start_date.asc(), ActivityDate.id.asc())
        .all()
    )
    return [
        ActivityDateSpan(
            activity=activity,
            row=row,
            start=row.start_date,
            end=row.end_date or row.start_date,
        )
        for row, activity in rows
    ]


def activity_dates_active_between(db: Session, start: date, end: date) -> list[ActivityDateSpan]:
    """Date rows that ran or started in the window [start, end).

    The same window as `activities_active_between`, one row further down: a
    monthly ride contributes every ride in the window, and a row that is still
    running — the photo hunt from June to September — counts as it did.
    """
    return _date_spans(db, lambda first, last: (first < end) & (last >= start))


def activity_dates_from(
    db: Session, day: date, until: Optional[date] = None
) -> list[ActivityDateSpan]:
    """Date rows starting on or after `day`, up to and including `until` if given."""
    conditions: list[Callable[[Any, Any], Any]] = [lambda first, last: first >= day]
    if until is not None:
        conditions.append(lambda first, last: first <= until)
    return _date_spans(db, *conditions)


def registration_counts(
    db: Session, activity_ids: list[int]
) -> dict[int, tuple[int, Optional[int]]]:
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
    caps = (
        db.query(
            ActivitySubRegistration.activity_id,
            func.sum(ActivitySubRegistration.max_participants),
            func.count(ActivitySubRegistration.max_participants),
        )
        .filter(ActivitySubRegistration.activity_id.in_(activity_ids))
        .group_by(ActivitySubRegistration.activity_id)
        .all()
    )
    capacity = {
        activity_id: (int(total) if capped else None) for activity_id, total, capped in caps
    }

    booked: dict[int, int] = {}
    component_owner = dict(
        db.query(ActivitySubRegistration.id, ActivitySubRegistration.activity_id)
        .filter(ActivitySubRegistration.activity_id.in_(activity_ids))
        .all()
    )
    for component_id, quantity in per_component.items():
        activity_id = component_owner.get(component_id)
        if activity_id is not None:
            booked[activity_id] = booked.get(activity_id, 0) + quantity
    # Registrations that hang on no component still count as attendance.
    loose = (
        db.query(Registration.activity_id, func.count(Registration.id))
        .filter(Registration.activity_id.in_(activity_ids), Registration.component_id.is_(None))
        .group_by(Registration.activity_id)
        .all()
    )
    for activity_id, count in loose:
        booked[activity_id] = booked.get(activity_id, 0) + int(count or 0)

    return {
        activity_id: (booked.get(activity_id, 0), capacity.get(activity_id))
        for activity_id in activity_ids
    }


def _booked_per_component(db: Session, activity_ids: list[int]) -> dict[int, int]:
    """Booked places per component: the sum of the item quantities, or one per
    registration without items. One batched query; the global soft-delete and
    tenant filters apply, so deleted registrations do not count."""
    from app.domains.activities.models import RegistrationItem

    if not activity_ids:
        return {}
    item_sum = (
        db.query(
            RegistrationItem.registration_id.label("rid"),
            func.sum(RegistrationItem.quantity).label("q"),
        )
        .group_by(RegistrationItem.registration_id)
        .subquery()
    )
    rows = (
        db.query(Registration.component_id, func.sum(func.coalesce(item_sum.c.q, 1)))
        .outerjoin(item_sum, item_sum.c.rid == Registration.id)
        .filter(Registration.activity_id.in_(activity_ids), Registration.component_id.isnot(None))
        .group_by(Registration.component_id)
        .all()
    )
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


def _organiser_rows(db: Session, activity_id: int) -> list[ActivityOrganiser]:
    from app.domains.activities.models import ActivityOrganiser

    return (
        db.query(ActivityOrganiser)
        .filter(ActivityOrganiser.activity_id == activity_id)
        .order_by(ActivityOrganiser.sort_order, ActivityOrganiser.id)
        .all()
    )


def organisers_for(db: Session, activity_id: int) -> list:
    """The organisers of one activity, in their own order (#1004)."""
    from app.domains.mdm.api import ContactDetail, Person

    rijen = _organiser_rows(db, activity_id)
    if not rijen:
        return []
    person_ids = [r.person_id for r in rijen]
    personen = {p.id: p for p in db.query(Person).filter(Person.id.in_(person_ids)).all()}
    contacten: dict[tuple[int, str | None], str] = {}
    for detail in db.query(ContactDetail).filter(ContactDetail.person_id.in_(person_ids)).all():
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
        gezien.append(
            OrganiserView(
                id=rij.id,
                person_id=rij.person_id,
                name=naam,
                is_contact=bool(rij.is_contact),
                email=email if rij.show_email else "",
                mobile=mobile if rij.show_mobile else "",
                email_override=rij.email_override or "",
                mobile_override=rij.mobile_override or "",
                show_email=bool(rij.show_email),
                show_mobile=bool(rij.show_mobile),
                sort_order=rij.sort_order,
            )
        )
    return gezien


def board_notes(db: Session, activity_id: int) -> str:
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


def add_organiser(db: Session, activity_id: int, person_id: int) -> ActivityOrganiser:
    """Add one organiser. Refuses a fourth, and someone who is no member."""
    from app.domains.activities.models import ActivityOrganiser
    from app.domains.mdm.api import Person, is_member
    from app.i18n import _

    if db.query(Activity).filter(Activity.id == activity_id).first() is None:
        raise LookupError("Activiteit niet gevonden")
    rijen = _organiser_rows(db, activity_id)
    if len(rijen) >= MAX_ORGANISERS:
        raise ActiviteitFout(
            _("Een activiteit heeft hoogstens %(n)s organisatoren.") % {"n": MAX_ORGANISERS}
        )
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
    rij = ActivityOrganiser(activity_id=activity_id, person_id=person_id, sort_order=volgende)
    db.add(rij)
    db.commit()
    db.refresh(rij)
    return rij


def update_organiser(
    db: Session, activity_id: int, organiser_id: int, velden: dict
) -> ActivityOrganiser:
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


def remove_organiser(db: Session, activity_id: int, organiser_id: int) -> bool:
    rij = next((r for r in _organiser_rows(db, activity_id) if r.id == organiser_id), None)
    if rij is None:
        return False
    db.delete(rij)
    db.commit()
    return True
