import logging
from datetime import date
from sqlalchemy import or_, and_, func, nulls_last
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response

logger = logging.getLogger(__name__)
from sqlalchemy.orm import Session, selectinload

from app.domains.auth.api import get_current_admin, get_current_member
from app.database import get_db
from app.domains.activities.models import ActivityDate, Activity, Registration, RegistrationItem
from app.domains.auth.api import User
from app.domains.activities.models import ActivitySubRegistration, ActivityProduct
from app.schemas.activity import (
    RegistrationContactUpdate,
    ActivityCreate,
    ActivityUpdate,
    ActivityResponse,
    ActivityDateCreate,
    ActivityDateUpdate,
    ActivityDateResponse,
    ComponentCreate,
    ComponentUpdate,
    ComponentResponse,
    ProductCreate,
    ProductUpdate,
    ProductResponse,
    RegistrationCreate,
    RegistrationResponse,
    RegistrationItemCreate,
    RegistrationItemUpdate,
)
from app.domains.mail.api import send_activity_registration_confirmation
from app.domains.activities.totals import compute_registration_total
from app.config import settings
from app.domains.payment.api import (
    create_payment_record, registration_balance, reconcile_registration_charges,
)
from app.domains.audit.api import (
    snapshot_registration,
    snapshot_registration_item,
    snapshot_activity,
    snapshot_activity_date,
    snapshot_component,
    snapshot_product,
)
from app.domains.activities.export import build_component_export_ods
from app.soft_delete import soft_delete
from app.limiter import registration_limiter
from app.i18n import _

router = APIRouter(tags=["activities"])


def _effective_end(ad: ActivityDate) -> date:
    return ad.end_date or ad.start_date


def _is_future(ad: ActivityDate, today: date) -> bool:
    return _effective_end(ad) >= today


def compute_activity_status(
    activity: Activity,
    registration_count: int | None = None,
) -> dict:
    if registration_count is None:
        registration_count = len(activity.registrations)

    today = date.today()
    all_past = not any(_is_future(d, today) for d in activity.dates)

    if all_past or not activity.dates:
        status = "Voorbij"
    elif activity.is_cancelled:
        status = "Geannuleerd"
    else:
        status = "Open"

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
    """Bezette plaatsen per onderdeel: som van item-hoeveelheden, of 1 per
    inschrijving zonder items (zelfde telling als de volzet-check bij inschrijven).
    Eén batched query; de globale soft-delete- en tenant-filters gelden ook hier,
    dus verwijderde inschrijvingen tellen niet mee."""
    occ: dict = {}
    if not activity_ids:
        return occ
    item_sum = (
        db.query(
            RegistrationItem.registration_id.label("rid"),
            func.sum(RegistrationItem.quantity).label("q"),
        )
        .group_by(RegistrationItem.registration_id)
        .subquery()
    )
    rows = (
        db.query(
            Registration.component_id,
            func.sum(func.coalesce(item_sum.c.q, 1)),
        )
        .outerjoin(item_sum, item_sum.c.rid == Registration.id)
        .filter(
            Registration.activity_id.in_(activity_ids),
            Registration.component_id.isnot(None),
        )
        .group_by(Registration.component_id)
        .all()
    )
    for component_id, qty in rows:
        occ[component_id] = int(qty or 0)
    return occ


def _mark_full(responses: List[ActivityResponse], occ: dict) -> None:
    """Zet ``is_full`` op elk onderdeel met een max dat (over)bereikt is."""
    for resp in responses:
        for comp in resp.sub_registrations:
            if comp.max_participants is not None:
                comp.is_full = occ.get(comp.id, 0) >= comp.max_participants


def _build_response(
    activity: Activity,
    today: date,
    for_archive: bool = False,
    all_dates: bool = False,
    reg_count: int = 0,
    status: str | None = None,
) -> ActivityResponse:
    sorted_dates = sorted(activity.dates, key=lambda d: d.start_date)
    # Publiek: homepage toont enkel de toekomstige datums, het archief enkel de
    # voorbije. Een activiteit met beide verschijnt in beide lijsten met het
    # relevante deel. Admin (all_dates) toont altijd álle datums.
    if for_archive:
        relevant = [d for d in sorted_dates if not _is_future(d, today)]
        sort_date = relevant[-1].start_date if relevant else (sorted_dates[-1].start_date if sorted_dates else None)
    else:
        relevant = [d for d in sorted_dates if _is_future(d, today)]
        sort_date = relevant[0].start_date if relevant else (sorted_dates[0].start_date if sorted_dates else None)
    shown = sorted_dates if all_dates else relevant
    resp = ActivityResponse.model_validate(activity)
    resp.dates = [ActivityDateResponse.model_validate(d) for d in shown]
    resp.sort_date = sort_date
    resp.status = status
    resp.registration_count = reg_count
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
    today = date.today()
    effective_end = func.coalesce(ActivityDate.end_date, ActivityDate.start_date)

    base = db.query(Activity).options(
        selectinload(Activity.dates),
        selectinload(Activity.sub_registrations).selectinload(ActivitySubRegistration.products),
    )

    if scope == "archived":
        has_past = (
            db.query(ActivityDate.id)
            .filter(ActivityDate.activity_id == Activity.id, effective_end < today)
            .correlate(Activity).exists()
        )
        sort_sq = (
            db.query(func.max(ActivityDate.start_date))
            .filter(ActivityDate.activity_id == Activity.id, effective_end < today)
            .correlate(Activity).scalar_subquery()
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
            .correlate(Activity).scalar_subquery()
        )
        past_sort = (
            db.query(func.max(ActivityDate.start_date))
            .filter(ActivityDate.activity_id == Activity.id, effective_end < today)
            .correlate(Activity).scalar_subquery()
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
            .correlate(Activity).exists()
        )
        sort_sq = (
            db.query(func.min(ActivityDate.start_date))
            .filter(ActivityDate.activity_id == Activity.id, effective_end >= today)
            .correlate(Activity).scalar_subquery()
        )
        activities = base.filter(has_future).order_by(sort_sq.asc()).all()

    counts = _registration_counts(db, [a.id for a in activities])
    result = []
    for a in activities:
        reg_count = counts.get(a.id, 0)
        if scope == "archived":
            # Archiefkaarten tonen enkel voorbije datums → status altijd Voorbij/Geannuleerd.
            status = "Geannuleerd" if a.is_cancelled else "Voorbij"
            result.append(_build_response(a, today, for_archive=True, reg_count=reg_count, status=status))
        else:
            info = compute_activity_status(a, reg_count)
            result.append(_build_response(a, today, all_dates=(scope == "all"), reg_count=reg_count, status=info["status"]))
    if scope != "archived":
        _mark_full(result, _component_occupancy(db, [a.id for a in activities]))
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
            selectinload(Activity.sub_registrations).selectinload(
                ActivitySubRegistration.products),
        )
        .filter(Activity.id == activity_id)
        .first()
    )
    if activity is None:
        return None
    today = date.today()
    reg_count = _registration_counts(db, [activity.id]).get(activity.id, 0)
    info = compute_activity_status(activity, reg_count)
    resp = _build_response(activity, today, all_dates=True, reg_count=reg_count,
                           status=info["status"])
    # Beide helpers nemen een lijst id's en zijn batched; met één id werken ze
    # even goed. Nagekeken omdat een berekening die stilzwijgend van de volledige
    # lijst afhangt, hier een lege bezetting zou geven.
    _mark_full([resp], _component_occupancy(db, [activity.id]))
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

    nieuw = service.create_activity(
        db, name=data.name, location=data.location, poster_url=data.poster_url,
        members_only=bool(data.members_only), dates=data.dates, actor=admin.email)
    activity = service._activity_met_boom(db, nieuw.id)
    assert activity is not None  # net aangemaakt in dezelfde transactie
    return _build_response(activity, date.today(), status="Open", reg_count=0)


@router.put("/activities/{activity_id}", response_model=ActivityResponse)
def update_activity(
    activity_id: int,
    data: ActivityUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    from app.domains.activities import service

    activity = service.update_activity(db, activity_id,
                                       data.model_dump(exclude_none=True),
                                       actor=admin.email)
    if activity is None:
        raise HTTPException(status_code=404, detail=_("Activity not found"))
    info = compute_activity_status(activity)
    return _build_response(activity, date.today(), status=info["status"],
                           reg_count=info["registration_count"])


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

    ad = service.add_activity_date(db, activity_id, data, actor=admin.email)
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

    ad = service.update_activity_date(db, activity_id, date_id,
                                      data.model_dump(exclude_unset=True),
                                      actor=admin.email)
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

    component = service.update_component(db, activity_id, component_id,
                                         data.model_dump(exclude_unset=True),
                                         actor=admin.email)
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

@router.post("/activities/{activity_id}/components/{component_id}/products", response_model=ProductResponse)
def add_product(
    activity_id: int,
    component_id: int,
    data: ProductCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    from app.domains.activities import service

    try:
        product = service.add_product(db, activity_id, component_id, data,
                                      actor=admin.email)
    except service.ActiviteitFout as fout:
        # De regel is een domeinregel; enkel de statuscode hoort hier.
        raise HTTPException(status_code=422, detail=str(fout))
    if product is None:
        raise HTTPException(status_code=404, detail=_("Component not found"))
    return product


@router.put("/activities/{activity_id}/components/{component_id}/products/{product_id}", response_model=ProductResponse)
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
        product = service.update_product(db, component_id, product_id,
                                         data.model_dump(exclude_unset=True),
                                         actor=admin.email)
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

    regs = service.registrations_for(db, activity_id, component_id=component_id,
                                     without_component=without_component)
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


def _load_registration_or_404(db: Session, activity: Activity, registration_id: int) -> Registration:
    reg = db.query(Registration).filter(
        Registration.id == registration_id,
        Registration.activity_id == activity.id,
    ).first()
    if not reg:
        raise HTTPException(status_code=404, detail=_("Registration not found"))
    return reg


def _validate_order_product(db: Session, activity: Activity, reg: Registration, product_id: int) -> ActivityProduct:
    """Een bestelregel mag enkel een product van dit onderdeel/deze activiteit bevatten."""
    product = db.query(ActivityProduct).filter(ActivityProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail=_("Product not found"))
    comp = db.query(ActivitySubRegistration).filter(
        ActivitySubRegistration.id == product.component_id
    ).first()
    if not comp or comp.activity_id != activity.id:
        raise HTTPException(status_code=400, detail=_("Product hoort niet bij deze activiteit."))
    if reg.component_id is not None and product.component_id != reg.component_id:
        raise HTTPException(status_code=400, detail=_("Product hoort niet bij het onderdeel van deze inschrijving."))
    return product


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
        reg = service.add_order_line(db, activity_id, registration_id,
                                     data.product_id, data.quantity,
                                     actor=admin.email)
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
        reg = service.update_order_line(db, activity_id, registration_id, item_id,
                                        product_id=data.product_id,
                                        quantity=data.quantity, actor=admin.email)
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
    reg = service.delete_order_line(db, activity_id, registration_id, item_id,
                                    actor=admin.email)
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
        db, activity_id, registration_id, data.model_dump(exclude_unset=True),
        actor=admin.email)
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
    if not service.delete_registration(db, activity_id, registration_id,
                                       actor=admin.email):
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
            result.append({
                "contact_name": reg.contact_name or "",
                "quantity": qty,
                "team_name": reg.team_name,
            })
    return result


@router.post("/activities/{activity_id}/register", response_model=RegistrationResponse, dependencies=[Depends(registration_limiter)])
def register_for_activity(
    activity_id: int,
    data: RegistrationCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_member=Depends(get_current_member),
):
    activity = (
        db.query(Activity)
        .options(selectinload(Activity.dates))
        .filter(Activity.id == activity_id)
        .first()
    )
    if not activity:
        raise HTTPException(status_code=404, detail=_("Activity not found"))

    today = date.today()
    if not any(_is_future(d, today) for d in activity.dates):
        raise HTTPException(status_code=400, detail=_("Activity is no longer open for registration"))

    if data.contact_email:
        existing_count = db.query(Registration).filter(
            Registration.activity_id == activity_id,
            Registration.component_id == data.component_id,
            func.lower(Registration.contact_email) == data.contact_email.lower(),
        ).count()
        from app.kernel.tenant_config import tenant_max_registrations_per_email
        max_regs = tenant_max_registrations_per_email(db)
        if existing_count >= max_regs:
            raise HTTPException(
                status_code=409,
                detail=_("Er zijn al %(max)s inschrijvingen met dit "
                         "e-mailadres voor dit onderdeel. Neem contact op met het bestuur als je er meer nodig hebt.")
                % {"max": max_regs},
            )

    valid_product_ids = {
        p.id for comp in activity.sub_registrations for p in comp.products
    }

    from app.kernel.tenant_config import tenant_max_item_quantity
    max_qty = tenant_max_item_quantity(db)
    for item_data in data.items:
        if item_data.product_id not in valid_product_ids:
            raise HTTPException(
                status_code=400,
                detail=_("Ongeldig product in de inschrijving."),
            )
        if item_data.quantity < 0 or item_data.quantity > max_qty:
            raise HTTPException(
                status_code=400,
                detail=_("Ongeldig aantal: kies een waarde tussen 0 en %(max)s.") % {"max": max_qty},
            )

    new_qty = sum(i.quantity for i in data.items) if data.items else 1

    if data.component_id:
        component = next(
            (c for c in activity.sub_registrations if c.id == data.component_id), None
        )
        if component and component.max_participants is not None:
            current_qty = 0
            for reg in activity.registrations:
                if reg.component_id != data.component_id:
                    continue
                current_qty += sum(it.quantity for it in reg.items) if reg.items else 1
            if current_qty + new_qty > component.max_participants:
                raise HTTPException(
                    status_code=400,
                    detail=_("Dit onderdeel is volzet. Inschrijven is niet meer mogelijk."),
                )

    registration = Registration(
        activity_id=activity_id,
        component_id=data.component_id,
        registration_type="INDIVIDUAL",
        contact_name=data.contact_name,
        contact_email=data.contact_email,
        phone=data.phone,
        team_name=data.team_name,
        payment_method=data.payment_method,
        remarks=data.remarks,
        person_id=current_member.id if current_member else None,
    )
    db.add(registration)
    db.flush()

    for item_data in data.items:
        if item_data.quantity > 0:
            item = RegistrationItem(
                registration_id=registration.id,
                product_id=item_data.product_id,
                quantity=item_data.quantity,
            )
            db.add(item)
            db.flush()
            # Auditeer de initiële bestelregels (#84), zodat latere wijzigingen
            # tegen een vastgelegde startsituatie afgezet kunnen worden.
            snapshot_registration_item(
                db, item,
                operation="insert", action="order_created", source="registration",
            )

    db.flush()
    db.refresh(registration)
    total_amount, _extra = compute_registration_total(registration)

    checkout_url = None
    payment_record = None
    if data.payment_method and total_amount > 0:
        method = "online" if data.payment_method == "ONLINE" else "transfer"
        from app.kernel.tenant_config import tenant_base_url

        redirect_url = f"{tenant_base_url(db)}/betaling/succes?registration={registration.id}"
        description = f"Inschrijving {activity.name} – {data.contact_name}"
        try:
            payment_record = create_payment_record(
                db=db,
                payable_type="registration",
                payable_id=registration.id,
                amount=total_amount,
                method=method,
                redirect_url=redirect_url,
                description=description,
                audit_source="registration",
            )
            if method == "online" and payment_record.gateway_payment_id:
                from app.domains.payment.api import GatewayPayment
                gp = db.query(GatewayPayment).filter(GatewayPayment.id == payment_record.gateway_payment_id).first()
                if gp:
                    checkout_url = gp.checkout_url
        except Exception as e:
            logger.error("Betaling aanmaken mislukt voor inschrijving (%s): %s", method, e)
            if method == "online":
                db.rollback()
                raise HTTPException(
                    status_code=502,
                    detail=_("De online betaling kon niet gestart worden. Je inschrijving is niet bewaard — probeer ze later opnieuw."),
                )

        if method == "online" and not checkout_url:
            db.rollback()
            raise HTTPException(
                status_code=502,
                detail=_("De online betaling kon niet gestart worden. Je inschrijving is niet bewaard — probeer ze later opnieuw."),
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
