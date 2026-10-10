import logging
from datetime import date
from typing import List, Optional

from fastapi import BackgroundTasks, HTTPException
from sqlalchemy import func, nulls_last
from sqlalchemy.orm import Session, selectinload

from app.domains.activities.models import (
    Activity,
    ActivityDate,
    ActivityError,
    ActivitySubRegistration,
    Registration,
    RegistrationLimitReached,
    RegistrationRefused,
)
from app.domains.activities.totals import compute_registration_total
from app.domains.mdm.api import CONTACT, PaymentMethod, Person
from app.domains.payment.api import (
    PayableType,
    create_payment_record,
)
from app.i18n import _
from app.kernel.clock import belgian_today
from app.kernel.contracts.activities import RegistrationConfirmed
from app.kernel.events import publish
from app.schemas.activity import (
    ActivityDateResponse,
    ActivityResponse,
    RegistrationCreate,
)

logger = logging.getLogger(__name__)

# No router since CR-13 phase 4b (#1251): every JSON route of the activities is
# gone, none had a caller. What is left are the functions the facade calls
# (`api.py`); phase 4c moves them out of this file.


def compute_activity_status(
    activity: Activity,
    registration_count: int | None = None,
) -> dict:
    if registration_count is None:
        registration_count = len(activity.registrations)

    # #977: het label volgt uit `registration_state`. Hier stond een eigen
    # berekening (voorbij / geannuleerd / open) naast die van de service — twee
    # plekken die "open" beslissen, en de deadline van #974 zat maar in één.
    from app.domains.activities.service import status_label

    status = status_label(activity)

    return {
        "status": status,
        "registration_count": registration_count,
    }


def _registration_counts(db: Session, activity_ids: List[int]) -> dict:
    """Aantal inschrijvingen per activiteit in één GROUP BY-query (vermijdt N+1)."""
    counts: dict = {aid: 0 for aid in activity_ids}
    if not activity_ids:
        return counts
    rows = (
        db.query(Registration.activity_id, func.count())
        .filter(Registration.activity_id.in_(activity_ids))
        .group_by(Registration.activity_id)
        .all()
    )
    for activity_id, cnt in rows:
        counts[activity_id] = cnt
    return counts


def _component_occupancy(db: Session, activity_ids: List[int]) -> dict:
    """Bezette plaatsen per onderdeel — de telling zelf staat in de service.

    Dezelfde regel ("som van de item-hoeveelheden, of 1 per inschrijving zonder
    items") beantwoordt ook de vraag van de vergaderagenda, per activiteit i.p.v.
    per onderdeel (#258). Ze staat daarom één keer, in de service; hier blijft de
    doorgang staan omdat de router-helper op vier plaatsen aangeroepen wordt.
    """
    from app.domains.activities.service import _booked_per_component

    return _booked_per_component(db, activity_ids)


def _mark_full(responses: List[ActivityResponse], occ: dict) -> None:
    """Zet ``is_full`` op elk onderdeel met een max dat (over)bereikt is."""
    for resp in responses:
        for comp in resp.sub_registrations:
            if comp.max_participants is not None:
                comp.is_full = occ.get(comp.id, 0) >= comp.max_participants


def _mark_card_deadline(responses: List[ActivityResponse]) -> None:
    """Vul `shared_deadline` — ná `_mark_full`, want ze leest `is_full` (#1053)."""
    from app.domains.activities.service import card_deadline, deadline_is_near

    for resp in responses:
        resp.shared_deadline = card_deadline(resp)
        resp.shared_deadline_near = deadline_is_near(resp.shared_deadline)
        for comp in resp.sub_registrations:
            comp.deadline_near = deadline_is_near(comp.registration_closes_on)


def _build_response(
    activity: Activity,
    today: date,
    for_archive: bool = False,
    all_dates: bool = False,
    reg_count: int = 0,
    status: str | None = None,
) -> ActivityResponse:
    from app.domains.activities.service import is_upcoming

    sorted_dates = sorted(activity.dates, key=lambda d: d.start_date)
    # Publiek: homepage toont enkel de toekomstige datums, het archief enkel de
    # voorbije. Een activiteit met beide verschijnt in beide lijsten met het
    # relevante deel. Admin (all_dates) toont altijd álle datums.
    if for_archive:
        relevant = [d for d in sorted_dates if not is_upcoming(d, today)]
        sort_date = (
            relevant[-1].start_date
            if relevant
            else (sorted_dates[-1].start_date if sorted_dates else None)
        )
    else:
        relevant = [d for d in sorted_dates if is_upcoming(d, today)]
        sort_date = (
            relevant[0].start_date
            if relevant
            else (sorted_dates[0].start_date if sorted_dates else None)
        )
    shown = sorted_dates if all_dates else relevant
    resp = ActivityResponse.model_validate(activity)
    resp.dates = [ActivityDateResponse.model_validate(d) for d in shown]
    resp.sort_date = sort_date
    resp.status = status
    resp.registration_count = reg_count
    # #974: de Belgische datum van de service, niet de `today` hierboven — die
    # bepaalt in welke LIJST een activiteit staat, niet of ze nog inschrijvingen
    # aanneemt.
    from app.domains.activities.service import registration_state

    resp.registration_state = registration_state(activity).value
    # #1053: en per onderdeel, want de barbecue mag een week eerder sluiten dan
    # cornhole. Gevraagd aan het ANTWOORD-onderdeel: dat draagt dezelfde datum,
    # dus er is geen tweede lus die op volgorde moet vertrouwen.
    for comp in resp.sub_registrations:
        comp.registration_state = registration_state(activity, component=comp).value
    return resp


# ── Activities ────────────────────────────────────────────────────────────────


def activities_for(
    db: Session, scope: str = "upcoming", *, include_drafts: bool = False
) -> List[ActivityResponse]:
    """The activities of a scope (#136), for the facade — the JSON route that
    also answered with it is gone (CR-13 phase 4b, #1251):

    - ``upcoming`` (default): activities with at least one date ahead, sorted on
      the next one; only the dates ahead are shown.
    - ``archived``: activities with at least one passed date, sorted on the most
      recent one; only the passed dates; the status is always "Voorbij".
    - ``all`` (the board): every activity with every date.

    `include_drafts` only for the board's own list (#1428)."""
    today = belgian_today()
    # "Passed" and "ahead" are the service's, the same comparison `registration_state`
    # makes (CR-13 phase 4).
    from app.domains.activities.service import date_passed, date_upcoming

    base = db.query(Activity).options(
        selectinload(Activity.dates),
        selectinload(Activity.sub_registrations).selectinload(ActivitySubRegistration.products),
        # The uploaded poster and info files, in one query each for the whole list
        # instead of one per card (CR-13 phase 4: the entity no longer queries).
        selectinload(Activity.poster_assets),
        selectinload(Activity.sub_registrations).selectinload(ActivitySubRegistration.info_assets),
    )
    # #1428: a draft is for the board only; every other caller gets none.
    if not include_drafts:
        from app.domains.activities.service import published_only

        base = base.filter(published_only())

    if scope == "archived":
        has_past = (
            db.query(ActivityDate.id)
            .filter(ActivityDate.activity_id == Activity.id, date_passed(today))
            .correlate(Activity)
            .exists()
        )
        sort_sq = (
            db.query(func.max(ActivityDate.start_date))
            .filter(ActivityDate.activity_id == Activity.id, date_passed(today))
            .correlate(Activity)
            .scalar_subquery()
        )
        activities = base.filter(has_past).order_by(sort_sq.desc()).all()
    elif scope == "all":
        # Admin (#186): toekomstige activiteiten eerst (de snelst komende bovenaan),
        # daarna de voorbije (meest recente eerst). Toekomst heeft een niet-lege
        # `upcoming_sort` → sorteert vooraan oplopend; voorbij-enkel valt op NULL en
        # komt erachter, aflopend op de meest recente voorbije datum.
        upcoming_sort = (
            db.query(func.min(ActivityDate.start_date))
            .filter(ActivityDate.activity_id == Activity.id, date_upcoming(today))
            .correlate(Activity)
            .scalar_subquery()
        )
        past_sort = (
            db.query(func.max(ActivityDate.start_date))
            .filter(ActivityDate.activity_id == Activity.id, date_passed(today))
            .correlate(Activity)
            .scalar_subquery()
        )
        activities = base.order_by(
            nulls_last(upcoming_sort.asc()),
            nulls_last(past_sort.desc()),
        ).all()
    else:  # upcoming (default)
        scope = "upcoming"
        has_future = (
            db.query(ActivityDate.id)
            .filter(ActivityDate.activity_id == Activity.id, date_upcoming(today))
            .correlate(Activity)
            .exists()
        )
        sort_sq = (
            db.query(func.min(ActivityDate.start_date))
            .filter(ActivityDate.activity_id == Activity.id, date_upcoming(today))
            .correlate(Activity)
            .scalar_subquery()
        )
        activities = base.filter(has_future).order_by(sort_sq.asc()).all()

    counts = _registration_counts(db, [a.id for a in activities])
    result = []
    for a in activities:
        reg_count = counts.get(a.id, 0)
        if scope == "archived":
            # Archiefkaarten tonen enkel voorbije datums → status altijd Voorbij/Geannuleerd.
            status = "Geannuleerd" if a.is_cancelled else "Voorbij"
            result.append(
                _build_response(a, today, for_archive=True, reg_count=reg_count, status=status)
            )
        else:
            info = compute_activity_status(a, reg_count)
            result.append(
                _build_response(
                    a, today, all_dates=(scope == "all"), reg_count=reg_count, status=info["status"]
                )
            )
    if scope != "archived":
        _mark_full(result, _component_occupancy(db, [a.id for a in activities]))
        _mark_card_deadline(result)
    return result


def get_activity_detail(db: Session, activity_id: int) -> Optional[ActivityResponse]:
    """Eén activiteit, met dezelfde verrijking als de lijst (#651).

    Het beheerdetail hergebruikte `list_activities(scope="all")` en filterde
    daarna in Python op id. Daardoor kostte het detail van ÉÉN activiteit meer dan
    de lijst van alle 167: gemeten op HDEV 483 ms tegenover 89 ms. En omdat het de
    gedeelde render-helper is, betaalde élke mutatie op dat scherm — datum
    opslaan, onderdeel toevoegen, volgorde wijzigen — die prijs opnieuw.

    Een kale query volstaat niet: het scherm heeft de verrijking wél nodig
    (`sort_date`, status, inschrijvingsaantal, `is_full` per onderdeel). Vandaar
    dezelfde bouwstenen als `list_activities`, maar gefilterd op id in SQL.

    `all_dates=True` is niet optioneel: het beheerscherm toont álle datums, ook de
    voorbije. Zonder die vlag zouden voorbije datums stil uit het detail
    verdwijnen — precies wat een herimplementatie makkelijk stukmaakt.
    """
    activity = (
        db.query(Activity)
        .options(
            selectinload(Activity.dates),
            selectinload(Activity.sub_registrations).selectinload(ActivitySubRegistration.products),
        )
        .filter(Activity.id == activity_id)
        .first()
    )
    if activity is None:
        return None
    today = belgian_today()
    reg_count = _registration_counts(db, [activity.id]).get(activity.id, 0)
    info = compute_activity_status(activity, reg_count)
    resp = _build_response(
        activity, today, all_dates=True, reg_count=reg_count, status=info["status"]
    )
    # Beide helpers nemen een lijst id's en zijn batched; met één id werken ze
    # even goed. Nagekeken omdat een berekening die stilzwijgend van de volledige
    # lijst afhangt, hier een lege bezetting zou geven.
    _mark_full([resp], _component_occupancy(db, [activity.id]))
    _mark_card_deadline([resp])
    return resp


# ── Registrations ─────────────────────────────────────────────────────────────


def get_public_registrations(activity_id: int, component_id: int, *, db: Session) -> list[dict]:
    """The public participant list of one component. No route of its own since
    CR-13 phase 4b (#1251): the activity card and page ask it through the facade."""
    from app.domains.activities.service import is_published

    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    # #1428: a draft has no public participant list.
    if not activity or not is_published(activity):
        raise HTTPException(status_code=404, detail=_("Activity not found"))

    result = []
    for reg in activity.registrations:
        if reg.component_id == component_id:
            qty = sum(item.quantity for item in reg.items) if reg.items else 1
            result.append(
                {
                    "contact_name": reg.contact_name or "",
                    "quantity": qty,
                    "team_name": reg.team_name,
                }
            )
    return result


def _inschrijver(current_member: Person | None) -> str:
    """Wie de inschrijving tekent (#713).

    Een aangemeld lid draagt zijn e-mailadres; is er niemand aangemeld, dan de
    publieke markering. Leeg laten zou "we weten het niet" betekenen, en dat is hier
    niet waar — de helft van de tijd weten we het wél.
    """
    from app.kernel.history import PUBLIC_ACTOR

    if current_member is None:
        return PUBLIC_ACTOR
    mail = next(
        (
            c.value
            for c in getattr(current_member, "contact_details", [])
            if c.contact_type_code == CONTACT.EMAIL
        ),
        None,
    )
    return mail or PUBLIC_ACTOR


# No route of its own since CR-13 phase 4b (#1251): the JSON door
# `POST /api/v1/activities/{id}/register` had no caller. This is the function behind
# `activities.api.register_for_activity`, which the public form calls; it stays here
# until phase 4c moves it to the service.
def register_for_activity(
    activity_id: int,
    data: RegistrationCreate,
    background_tasks: BackgroundTasks,
    *,
    db: Session,
    current_member: Person | None,
) -> dict:
    """The public way in: the registration hangs on whoever is signed in."""
    return create_registration(
        db,
        activity_id,
        data,
        background_tasks,
        person_id=current_member.id if current_member else None,
        actor=_inschrijver(current_member),
    )


def create_registration(
    db: Session,
    activity_id: int,
    data: RegistrationCreate,
    background_tasks: BackgroundTasks,
    *,
    person_id: int | None,
    actor: str,
    backoffice_products: bool = False,
    return_path: str = "/betaling/succes?registration={registration_id}",
) -> dict:
    """Create one registration: the ONE implementation (#1192).

    Two ways in, one body. The public form and the JSON API go through
    `register_for_activity`; the board's "add a registration" screen goes through
    `activities.api.board_register_for_activity`. Two copies of this function
    would drift apart on exactly the rule that matters within half a year — the
    duplication rule of CLAUDE.md.

    **Who sends the form is not who the registration is for.** The public way
    hangs it on the signed-in member; the board registers somebody else, so its
    way passes the person found by the e-mail address typed into the form (#1284),
    or None, and its own e-mail only as the audit `actor`. Taking the session's
    person here would make the board member a participant in every report that
    groups by person — and pricing by one person while saving another would show
    one total and charge a different one (`compute_registration_total` prices by
    `registration.person`).

    **What differs per way in, and nothing else** (#1284, Koen, 28 September
    2026: the board's form is the public one, "met uitzondering van de
    terugroutering en de producten die enkel in de backoffice zichtbaar zijn"):

    - `backoffice_products` — the back office may book products that are not
      publicly bookable (#1191), as `check_publicly_bookable`'s own comment
      says. #1192 also lifted the limit per e-mail address for the board; #1284
      put it back, so it holds on both ways;
    - `return_path` — where Mollie sends the payer back. The public way returns
      to the public page, the board to the registration in the back office.

    Everything else holds on both ways: the required fields (the registration's
    own validators and `check()`, Koen: "bestuur moet dezelfde velden
    invullen"), a closed or cancelled activity, a full component, the quantity
    limits, and the payment record of a paid product.
    """
    activity = (
        db.query(Activity)
        .options(selectinload(Activity.dates))
        .filter(Activity.id == activity_id)
        .first()
    )
    if not activity:
        raise HTTPException(status_code=404, detail=_("Activity not found"))

    # CR-13 phase 1: every rule of a registration is the service's now; this door
    # turns a refusal into the answer it gave before — a missing field 422, the
    # limit per e-mail address 409, any other refusal 400.
    from app.domains.activities.service import register

    try:
        registration = register(
            db,
            activity,
            data,
            person_id=person_id,
            actor=actor,
            backoffice_products=backoffice_products,
        )
    except RegistrationLimitReached as refusal:
        raise HTTPException(status_code=409, detail=str(refusal))
    except RegistrationRefused as refusal:
        raise HTTPException(status_code=400, detail=str(refusal))
    except ActivityError as refusal:
        raise HTTPException(status_code=422, detail=str(refusal))

    total_amount, _extra = compute_registration_total(registration)

    checkout_url = None
    payment_record = None
    if data.payment_method and total_amount > 0:
        # CR-12 phase 1: this used to read `"online" if data.payment_method == "ONLINE"
        # else "transfer"` — a translation between two spellings of one list.
        # Now that the form posts the codes itself, there is nothing left to
        # translate, and that is exactly what removes the duplication instead of
        # repairing it.
        method = PaymentMethod(data.payment_method)
        from app.kernel.tenant_config import tenant_base_url

        redirect_url = f"{tenant_base_url(db)}{return_path.format(registration_id=registration.id)}"
        description = f"Inschrijving {activity.name} – {data.contact_name}"
        try:
            # A call at the door, not an event handler (CR-13 phase 2, master CLI): an online payment
            # reaches the provider, the route needs the checkout URL now, and a failure rolls
            # the whole request back with a 502 — none of which a handler may do.
            payment_record = create_payment_record(
                db=db,
                payable_type=PayableType.REGISTRATION,
                payable_id=registration.id,
                amount=total_amount,
                method=method,
                redirect_url=redirect_url,
                description=description,
                audit_source="registration",
            )
            if method == PaymentMethod.ONLINE and payment_record.gateway_payment_id:
                from app.domains.payment.api import GatewayPayment

                gp = (
                    db.query(GatewayPayment)
                    .filter(GatewayPayment.id == payment_record.gateway_payment_id)
                    .first()
                )
                if gp:
                    checkout_url = gp.checkout_url
        except Exception as e:
            logger.error("Betaling aanmaken mislukt voor inschrijving (%s): %s", method, e)
            if method == PaymentMethod.ONLINE:
                db.rollback()
                raise HTTPException(
                    status_code=502,
                    detail=_(
                        "De online betaling kon niet gestart worden. Je inschrijving is niet bewaard — probeer ze later opnieuw."
                    ),
                )

        if method == PaymentMethod.ONLINE and not checkout_url:
            db.rollback()
            raise HTTPException(
                status_code=502,
                detail=_(
                    "De online betaling kon niet gestart worden. Je inschrijving is niet bewaard — probeer ze later opnieuw."
                ),
            )

    # Business-event (#152): inschrijving voltooid. Geen PII — enkel niet-
    # identificerende context. Commit mee in dezelfde transactie.

    # CR-13 phase 4: the confirmation is an event, in this transaction — `mail`
    # queues it as a job, so it leaves after the commit and never for a
    # registration that was rolled back.
    if data.contact_email:
        publish(
            RegistrationConfirmed(
                registration_id=registration.id,
                to_email=data.contact_email,
                name=data.contact_name or "Deelnemer",
                payment_record_id=payment_record.id if payment_record is not None else None,
            ),
            db,
        )

    db.commit()
    db.refresh(registration)

    from app.domains.activities.service import enrich_registration

    result = enrich_registration(registration, activity)
    result["checkout_url"] = checkout_url
    return result
