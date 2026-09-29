import logging
from datetime import date
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from sqlalchemy import func, nulls_last
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
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
from app.domains.auth.api import User, get_current_admin, get_current_member
from app.domains.mail.api import send_activity_registration_confirmation
from app.domains.mdm.api import CONTACT, PaymentMethod
from app.domains.payment.api import (
    PayableType,
    create_payment_record,
    registration_balance,
)
from app.i18n import _
from app.kernel.clock import belgian_today
from app.limiter import registration_limiter
from app.schemas.activity import (
    ActivityCreate,
    ActivityDateCreate,
    ActivityDateResponse,
    ActivityDateUpdate,
    ActivityResponse,
    ActivityUpdate,
    ComponentCreate,
    ComponentResponse,
    ComponentUpdate,
    ProductCreate,
    ProductResponse,
    ProductUpdate,
    RegistrationContactUpdate,
    RegistrationCreate,
    RegistrationItemCreate,
    RegistrationItemUpdate,
    RegistrationResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["activities"])


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


@router.get("/activities", response_model=List[ActivityResponse])
def list_activities(scope: str = "upcoming", db: Session = Depends(get_db)):
    """Eén endpoint met een scope-param (#136):
    - ``upcoming`` (default): activiteiten met ≥1 toekomstige datum, gesorteerd op
      de eerstvolgende datum; enkel de toekomstige datums worden getoond.
    - ``archived``: activiteiten met ≥1 voorbije datum, gesorteerd op de meest
      recente voorbije datum; enkel de voorbije datums; status altijd Voorbij.
    - ``all`` (admin): álle activiteiten met álle datums.
    """
    today = belgian_today()
    effective_end = func.coalesce(ActivityDate.end_date, ActivityDate.start_date)

    base = db.query(Activity).options(
        selectinload(Activity.dates),
        selectinload(Activity.sub_registrations).selectinload(ActivitySubRegistration.products),
    )

    if scope == "archived":
        has_past = (
            db.query(ActivityDate.id)
            .filter(ActivityDate.activity_id == Activity.id, effective_end < today)
            .correlate(Activity)
            .exists()
        )
        sort_sq = (
            db.query(func.max(ActivityDate.start_date))
            .filter(ActivityDate.activity_id == Activity.id, effective_end < today)
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
            .filter(ActivityDate.activity_id == Activity.id, effective_end >= today)
            .correlate(Activity)
            .scalar_subquery()
        )
        past_sort = (
            db.query(func.max(ActivityDate.start_date))
            .filter(ActivityDate.activity_id == Activity.id, effective_end < today)
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
            .filter(ActivityDate.activity_id == Activity.id, effective_end >= today)
            .correlate(Activity)
            .exists()
        )
        sort_sq = (
            db.query(func.min(ActivityDate.start_date))
            .filter(ActivityDate.activity_id == Activity.id, effective_end >= today)
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


@router.post("/activities", response_model=ActivityResponse)
def create_activity(
    data: ActivityCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    # #679: het aanmaken zelf (velden, datums, audit-snapshots, commit) staat in
    # de service. Wat hier overblijft is HTTP: het schema uitpakken en de respons
    # vormgeven.
    from app.domains.activities import service

    try:
        nieuw = service.create_activity(
            db,
            name=data.name,
            location=data.location,
            poster_url=data.poster_url,
            description=data.description,
            members_only=bool(data.members_only),
            dates=data.dates,
            actor=admin.email,
        )
    except service.ActiviteitFout as fout:
        raise HTTPException(status_code=422, detail=str(fout))
    activity = service._activity_met_boom(db, nieuw.id)
    assert activity is not None  # net aangemaakt in dezelfde transactie
    # #977: ook een verse activiteit krijgt het label van de service en niet een vast
    # "Open" — ze kan met een voorbije deadline of een voorbije datum aangemaakt zijn.
    info = compute_activity_status(activity, 0)
    return _build_response(activity, belgian_today(), status=info["status"], reg_count=0)


@router.put("/activities/{activity_id}", response_model=ActivityResponse)
def update_activity(
    activity_id: int,
    data: ActivityUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    from app.domains.activities import service

    velden = data.model_dump(exclude_none=True)
    activity = service.update_activity(db, activity_id, velden, actor=admin.email)
    if activity is None:
        raise HTTPException(status_code=404, detail=_("Activity not found"))
    info = compute_activity_status(activity)
    return _build_response(
        activity, belgian_today(), status=info["status"], reg_count=info["registration_count"]
    )


@router.delete("/activities/{activity_id}")
def delete_activity(
    activity_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    from app.domains.activities import service

    if not service.delete_activity(db, activity_id, actor=admin.email):
        raise HTTPException(status_code=404, detail=_("Activity not found"))
    return {"detail": "deleted"}


# ── Activity dates ────────────────────────────────────────────────────────────


@router.post("/activities/{activity_id}/dates", response_model=ActivityDateResponse)
def add_activity_date(
    activity_id: int,
    data: ActivityDateCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    from app.domains.activities import service

    # #792: the coherence rule sits on the object, so this entrance inherits it. The
    # translation into a status code does belong to the entrance.
    try:
        ad = service.add_activity_date(db, activity_id, data, actor=admin.email)
    except service.ActiviteitFout as fout:
        raise HTTPException(status_code=422, detail=str(fout))
    if ad is None:
        raise HTTPException(status_code=404, detail=_("Activity not found"))
    return ad


@router.put("/activities/{activity_id}/dates/{date_id}", response_model=ActivityDateResponse)
def update_activity_date(
    activity_id: int,
    date_id: int,
    data: ActivityDateUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    from app.domains.activities import service

    try:
        ad = service.update_activity_date(
            db, activity_id, date_id, data.model_dump(exclude_unset=True), actor=admin.email
        )
    except service.ActiviteitFout as fout:
        raise HTTPException(status_code=422, detail=str(fout))
    if ad is None:
        raise HTTPException(status_code=404, detail=_("Date not found"))
    return ad


@router.delete("/activities/{activity_id}/dates/{date_id}")
def delete_activity_date(
    activity_id: int,
    date_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    from app.domains.activities import service

    if not service.delete_activity_date(db, activity_id, date_id, actor=admin.email):
        raise HTTPException(status_code=404, detail=_("Date not found"))
    return {"detail": "deleted"}


# ── Components (Onderdelen) ───────────────────────────────────────────────────


@router.post("/activities/{activity_id}/components", response_model=ComponentResponse)
def add_component(
    activity_id: int,
    data: ComponentCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    from app.domains.activities import service

    component = service.add_component(db, activity_id, data, actor=admin.email)
    if component is None:
        raise HTTPException(status_code=404, detail=_("Activity not found"))
    return component


@router.put("/activities/{activity_id}/components/{component_id}", response_model=ComponentResponse)
def update_component(
    activity_id: int,
    component_id: int,
    data: ComponentUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    from app.domains.activities import service

    component = service.update_component(
        db, activity_id, component_id, data.model_dump(exclude_unset=True), actor=admin.email
    )
    if component is None:
        raise HTTPException(status_code=404, detail=_("Component not found"))
    return component


@router.delete("/activities/{activity_id}/components/{component_id}")
def delete_component(
    activity_id: int,
    component_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    from app.domains.activities import service

    if not service.delete_component(db, activity_id, component_id, actor=admin.email):
        raise HTTPException(status_code=404, detail=_("Component not found"))
    return {"detail": "deleted"}


# ── Products ──────────────────────────────────────────────────────────────────


@router.post(
    "/activities/{activity_id}/components/{component_id}/products", response_model=ProductResponse
)
def add_product(
    activity_id: int,
    component_id: int,
    data: ProductCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    from app.domains.activities import service

    try:
        product = service.add_product(db, activity_id, component_id, data, actor=admin.email)
    except service.ActiviteitFout as fout:
        # De regel is een domeinregel; enkel de statuscode hoort hier.
        raise HTTPException(status_code=422, detail=str(fout))
    if product is None:
        raise HTTPException(status_code=404, detail=_("Component not found"))
    return product


@router.put(
    "/activities/{activity_id}/components/{component_id}/products/{product_id}",
    response_model=ProductResponse,
)
def update_product(
    activity_id: int,
    component_id: int,
    product_id: int,
    data: ProductUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    from app.domains.activities import service

    try:
        product = service.update_product(
            db, component_id, product_id, data.model_dump(exclude_unset=True), actor=admin.email
        )
    except service.ActiviteitFout as fout:
        raise HTTPException(status_code=422, detail=str(fout))
    if product is None:
        raise HTTPException(status_code=404, detail=_("Product not found"))
    return product


@router.delete("/activities/{activity_id}/components/{component_id}/products/{product_id}")
def delete_product(
    activity_id: int,
    component_id: int,
    product_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    from app.domains.activities import service

    if not service.delete_product(db, component_id, product_id, actor=admin.email):
        raise HTTPException(status_code=404, detail=_("Product not found"))
    return {"detail": "deleted"}


# ── Registrations ─────────────────────────────────────────────────────────────


def _enrich_registration(reg, activity):
    """Verrijkte inschrijving zoals het scherm ze toont — implementatie in de
    service (#679, batch 6)."""
    from app.domains.activities import service

    return service.enrich_registration(reg, activity)


@router.get("/activities/{activity_id}/registrations", response_model=List[RegistrationResponse])
def get_registrations(
    activity_id: int,
    component_id: Optional[int] = None,
    without_component: bool = False,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    from app.domains.activities import service

    regs = service.registrations_for(
        db, activity_id, component_id=component_id, without_component=without_component
    )
    if regs is None:
        raise HTTPException(status_code=404, detail=_("Activity not found"))
    return regs


# ── OpenDocument-export per onderdeel (#85/#200) ──────────────────────────────


@router.get("/activities/{activity_id}/components/{component_id}/export")
def export_component_ods(
    activity_id: int,
    component_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Download een .ods met aantallen per product + financials voor één
    onderdeel, zoals ze nu in de DB staan (#85). Admin-only; bevat persoons- en
    financiële data."""
    from app.domains.activities import service

    resultaat = service.component_export(db, activity_id, component_id)
    if resultaat is None:
        raise HTTPException(status_code=404, detail=_("Component not found"))
    content, bestandsnaam = resultaat
    return Response(
        content=content,
        media_type="application/vnd.oasis.opendocument.spreadsheet",
        headers={"Content-Disposition": f'attachment; filename="{bestandsnaam}"'},
    )


# ── Bestelregels bewerken (admin) + audit (#84) ───────────────────────────────


def _load_activity_or_404(db: Session, activity_id: int) -> Activity:
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if not activity:
        raise HTTPException(status_code=404, detail=_("Activity not found"))
    return activity


def _load_registration_or_404(
    db: Session, activity: Activity, registration_id: int
) -> Registration:
    reg = (
        db.query(Registration)
        .filter(
            Registration.id == registration_id,
            Registration.activity_id == activity.id,
        )
        .first()
    )
    if not reg:
        raise HTTPException(status_code=404, detail=_("Registration not found"))
    return reg


def _order_edit_result(
    db: Session, activity: Activity, reg: Registration, actor: str | None = None
) -> dict:
    """Geef de vernieuwde bestelling + financiële stand terug; signaleert of er nu
    een terugbetaling openstaat (saldo < 0) zodat de UI naar de refund-flow kan wijzen.

    Het reconciliëren zelf staat sinds #679 in de service, bij de mutatie waar het
    hoort: wie een bestelregel wijzigt zonder te herrekenen laat het saldo stil
    verkeerd staan, en die regel moet gelden voor élke ingang. Wat hier overblijft
    is het vormgeven van het antwoord."""
    db.refresh(reg)
    bal = registration_balance(db, reg)
    return {
        "registration": _enrich_registration(reg, activity),
        "balance": bal,
        "refund_due": bal["balance"] < 0,
    }


@router.post("/activities/{activity_id}/registrations/{registration_id}/items")
def add_order_line(
    activity_id: int,
    registration_id: int,
    data: RegistrationItemCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    from app.domains.activities import service

    activity = _load_activity_or_404(db, activity_id)
    try:
        reg = service.add_order_line(
            db, activity_id, registration_id, data.product_id, data.quantity, actor=admin.email
        )
    except service.ActiviteitFout as fout:
        raise HTTPException(status_code=400, detail=str(fout))
    if reg is None:
        raise HTTPException(status_code=404, detail=_("Registration not found"))
    return _order_edit_result(db, activity, reg, actor=admin.email)


@router.patch("/activities/{activity_id}/registrations/{registration_id}/items/{item_id}")
def update_order_line(
    activity_id: int,
    registration_id: int,
    item_id: int,
    data: RegistrationItemUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    from app.domains.activities import service

    activity = _load_activity_or_404(db, activity_id)
    try:
        reg = service.update_order_line(
            db,
            activity_id,
            registration_id,
            item_id,
            product_id=data.product_id,
            quantity=data.quantity,
            actor=admin.email,
        )
    except service.ActiviteitFout as fout:
        raise HTTPException(status_code=400, detail=str(fout))
    if reg is None:
        raise HTTPException(status_code=404, detail=_("Order line not found"))
    return _order_edit_result(db, activity, reg, actor=admin.email)


@router.delete("/activities/{activity_id}/registrations/{registration_id}/items/{item_id}")
def delete_order_line(
    activity_id: int,
    registration_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    from app.domains.activities import service

    activity = _load_activity_or_404(db, activity_id)
    reg = service.delete_order_line(db, activity_id, registration_id, item_id, actor=admin.email)
    if reg is None:
        raise HTTPException(status_code=404, detail=_("Order line not found"))
    return _order_edit_result(db, activity, reg, actor=admin.email)


@router.patch("/activities/{activity_id}/registrations/{registration_id}")
def update_registration_remarks(
    activity_id: int,
    registration_id: int,
    data: RegistrationContactUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Admin corrigeert de contactgegevens en/of de opmerking (#283, uitgebreid #624).

    Raakt bestelregels, saldo en OGM NIET aan — dit is geen geldwijziging. Leeg of
    enkel witruimte → NULL. Soft-deleted inschrijvingen zijn via de globale filter
    onzichtbaar → 404 (niet bewerkbaar).

    Enkel meegestuurde velden veranderen: wie alleen `remarks` post, laat de
    contactgegevens ongemoeid — zo blijft de oude #283-aanroep werken.

    Elke wijziging krijgt een audit-snapshot; zonder spoor is een stille correctie op
    iemands contactgegevens niet te verklaren. De gekoppelde `Person` blijft
    ongemoeid: die corrigeer je op /admin/leden.
    """
    from app.domains.activities import service

    activity = _load_activity_or_404(db, activity_id)
    reg = service.update_registration_contact(
        db, activity_id, registration_id, data.model_dump(exclude_unset=True), actor=admin.email
    )
    if reg is None:
        raise HTTPException(status_code=404, detail=_("Registration not found"))
    return _enrich_registration(reg, activity)


@router.delete("/activities/{activity_id}/registrations/{registration_id}")
def delete_registration(
    activity_id: int,
    registration_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Verwijder (soft-delete) een hele inschrijving incl. haar bestelregels (#313).

    Raakt de betaling NIET aan: een ``PaymentRecord`` is een financieel feit en
    blijft bestaan én zichtbaar in het betaaloverzicht (de enrichment haalt ook
    soft-deleted inschrijvingen op via ``include_deleted``, #190). De bestelregels
    worden mee soft-deleted (met audit-snapshot) zodat ze niet in aantal-/
    saldoberekeningen lekken (#194)."""
    from app.domains.activities import service

    _load_activity_or_404(db, activity_id)
    if not service.delete_registration(db, activity_id, registration_id, actor=admin.email):
        raise HTTPException(status_code=404, detail=_("Registration not found"))
    return {"status": "deleted", "registration_id": registration_id}


@router.get("/activities/{activity_id}/public-registrations")
def get_public_registrations(
    activity_id: int,
    component_id: int,
    db: Session = Depends(get_db),
):
    """Return public participant list for a given component."""
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if not activity:
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


def _inschrijver(current_member) -> str:
    """Wie de inschrijving tekent (#713).

    Een aangemeld lid draagt zijn e-mailadres; is er niemand aangemeld, dan de
    publieke markering. Leeg laten zou "we weten het niet" betekenen, en dat is hier
    niet waar — de helft van de tijd weten we het wél.
    """
    from app.domains.audit.api import PUBLIEKE_ACTOR

    if current_member is None:
        return PUBLIEKE_ACTOR
    mail = next(
        (
            c.value
            for c in getattr(current_member, "contact_details", [])
            if c.contact_type_code == CONTACT.EMAIL
        ),
        None,
    )
    return mail or PUBLIEKE_ACTOR


@router.post(
    "/activities/{activity_id}/register",
    response_model=RegistrationResponse,
    dependencies=[Depends(registration_limiter)],
)
def register_for_activity(
    activity_id: int,
    data: RegistrationCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_member=Depends(get_current_member),
):
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
):
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

    db.commit()
    db.refresh(registration)

    if data.contact_email:
        try:
            send_activity_registration_confirmation(
                to_email=data.contact_email,
                name=data.contact_name or "Deelnemer",
                activity=activity,
                registration=registration,
                background_tasks=background_tasks,
                payment_record=payment_record,
            )
        except Exception as e:
            logger.error("Activiteit bevestigingsmail mislukt naar %s: %s", data.contact_email, e)

    result = _enrich_registration(registration, activity)
    result["checkout_url"] = checkout_url
    return result
