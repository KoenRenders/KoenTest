import logging
from datetime import date
from sqlalchemy import or_, and_, func
from typing import List

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response

logger = logging.getLogger(__name__)
from sqlalchemy.orm import Session, selectinload

from app.auth import get_current_admin, get_current_member
from app.database import get_db
from app.models.activity import ActivityDate, Activity, Registration, RegistrationItem
from app.models.user import User
from app.models.activity_sub_registration import ActivitySubRegistration, ActivityProduct
from app.schemas.activity import (
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
from app.services.email import send_activity_registration_confirmation
from app.services.registration_totals import compute_registration_total
from app.config import settings
from app.domains.payment_status.service import create_payment_record, registration_balance
from app.domains.analytics.service import log_business_event
from app.domains.audit.service import snapshot_registration_item
from app.services.activity_export import build_component_export_xlsx
from app.soft_delete import soft_delete
from app.limiter import registration_limiter

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
        sort_sq = (
            db.query(func.max(ActivityDate.start_date))
            .filter(ActivityDate.activity_id == Activity.id)
            .correlate(Activity).scalar_subquery()
        )
        activities = base.order_by(sort_sq.desc()).all()
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
    return result


@router.post("/activities", response_model=ActivityResponse)
def create_activity(
    data: ActivityCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    activity = Activity(
        name=data.name,
        location=data.location,
        poster_url=data.poster_url,
        members_only=bool(data.members_only),
    )
    db.add(activity)
    db.flush()

    for date_data in data.dates:
        db.add(ActivityDate(
            activity_id=activity.id,
            start_date=date_data.start_date,
            end_date=date_data.end_date,
            start_time=date_data.start_time,
            end_time=date_data.end_time,
        ))

    db.commit()

    activity = (
        db.query(Activity)
        .options(
            selectinload(Activity.dates),
            selectinload(Activity.sub_registrations).selectinload(ActivitySubRegistration.products),
        )
        .filter(Activity.id == activity.id)
        .first()
    )

    today = date.today()
    resp = _build_response(activity, today, status="Open", reg_count=0)
    return resp


@router.put("/activities/{activity_id}", response_model=ActivityResponse)
def update_activity(
    activity_id: int,
    data: ActivityUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    activity = (
        db.query(Activity)
        .options(
            selectinload(Activity.dates),
            selectinload(Activity.sub_registrations).selectinload(ActivitySubRegistration.products),
        )
        .filter(Activity.id == activity_id)
        .first()
    )
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(activity, field, value)
    db.commit()
    db.refresh(activity)

    today = date.today()
    info = compute_activity_status(activity)
    return _build_response(activity, today, status=info["status"], reg_count=info["registration_count"])


@router.delete("/activities/{activity_id}")
def delete_activity(
    activity_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    # Soft delete (#166): de hele boom mee markeren (datums, onderdelen, producten,
    # inschrijvingen, bestelregels). Betalingen blijven bestaan (financieel feit).
    for d in activity.dates:
        soft_delete(d)
    for comp in activity.sub_registrations:
        for p in comp.products:
            soft_delete(p)
        soft_delete(comp)
    for reg in activity.registrations:
        for item in reg.items:
            soft_delete(item)
        soft_delete(reg)
    soft_delete(activity)
    db.commit()
    return {"detail": "deleted"}


# ── Activity dates ────────────────────────────────────────────────────────────

@router.post("/activities/{activity_id}/dates", response_model=ActivityDateResponse)
def add_activity_date(
    activity_id: int,
    data: ActivityDateCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    ad = ActivityDate(
        activity_id=activity_id,
        start_date=data.start_date,
        end_date=data.end_date,
        start_time=data.start_time,
        end_time=data.end_time,
    )
    db.add(ad)
    db.commit()
    db.refresh(ad)
    return ad


@router.put("/activities/{activity_id}/dates/{date_id}", response_model=ActivityDateResponse)
def update_activity_date(
    activity_id: int,
    date_id: int,
    data: ActivityDateUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    ad = db.query(ActivityDate).filter(
        ActivityDate.id == date_id,
        ActivityDate.activity_id == activity_id,
    ).first()
    if not ad:
        raise HTTPException(status_code=404, detail="Date not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(ad, field, value)
    db.commit()
    db.refresh(ad)
    return ad


@router.delete("/activities/{activity_id}/dates/{date_id}")
def delete_activity_date(
    activity_id: int,
    date_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    ad = db.query(ActivityDate).filter(
        ActivityDate.id == date_id,
        ActivityDate.activity_id == activity_id,
    ).first()
    if not ad:
        raise HTTPException(status_code=404, detail="Date not found")
    soft_delete(ad)
    db.commit()
    return {"detail": "deleted"}


# ── Components (Onderdelen) ───────────────────────────────────────────────────

@router.post("/activities/{activity_id}/components", response_model=ComponentResponse)
def add_component(
    activity_id: int,
    data: ComponentCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    component = ActivitySubRegistration(
        activity_id=activity_id,
        name=data.name,
        team_name_required=data.team_name_required,
        sort_order=data.sort_order,
        external_register_url=data.external_register_url,
        external_registrations_url=data.external_registrations_url,
        info_url=data.info_url,
        max_participants=data.max_participants,
        registration_type_code="INDIVIDUAL",  # required FK, kept for DB compat
        price=0,
        is_free=True,
    )
    db.add(component)
    db.commit()
    db.refresh(component)
    return component


@router.put("/activities/{activity_id}/components/{component_id}", response_model=ComponentResponse)
def update_component(
    activity_id: int,
    component_id: int,
    data: ComponentUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    component = db.query(ActivitySubRegistration).filter(
        ActivitySubRegistration.id == component_id,
        ActivitySubRegistration.activity_id == activity_id,
    ).first()
    if not component:
        raise HTTPException(status_code=404, detail="Component not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(component, field, value)
    db.commit()
    db.refresh(component)
    return component


@router.delete("/activities/{activity_id}/components/{component_id}")
def delete_component(
    activity_id: int,
    component_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    component = db.query(ActivitySubRegistration).filter(
        ActivitySubRegistration.id == component_id,
        ActivitySubRegistration.activity_id == activity_id,
    ).first()
    if not component:
        raise HTTPException(status_code=404, detail="Component not found")
    for p in component.products:
        soft_delete(p)
    soft_delete(component)
    db.commit()
    return {"detail": "deleted"}


# ── Products ──────────────────────────────────────────────────────────────────

@router.post("/activities/{activity_id}/components/{component_id}/products", response_model=ProductResponse)
def add_product(
    activity_id: int,
    component_id: int,
    data: ProductCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    component = db.query(ActivitySubRegistration).filter(
        ActivitySubRegistration.id == component_id,
        ActivitySubRegistration.activity_id == activity_id,
    ).first()
    if not component:
        raise HTTPException(status_code=404, detail="Component not found")
    product = ActivityProduct(
        component_id=component_id,
        name=data.name,
        price=data.price,
        member_price=data.member_price,
        is_free=data.is_free,
        max_participants=data.max_participants,
        sort_order=data.sort_order,
    )
    db.add(product)
    db.commit()
    db.refresh(product)
    return product


@router.put("/activities/{activity_id}/components/{component_id}/products/{product_id}", response_model=ProductResponse)
def update_product(
    activity_id: int,
    component_id: int,
    product_id: int,
    data: ProductUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    product = db.query(ActivityProduct).filter(
        ActivityProduct.id == product_id,
        ActivityProduct.component_id == component_id,
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(product, field, value)
    db.commit()
    db.refresh(product)
    return product


@router.delete("/activities/{activity_id}/components/{component_id}/products/{product_id}")
def delete_product(
    activity_id: int,
    component_id: int,
    product_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    product = db.query(ActivityProduct).filter(
        ActivityProduct.id == product_id,
        ActivityProduct.component_id == component_id,
    ).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    soft_delete(product)
    db.commit()
    return {"detail": "deleted"}


# ── Registrations ─────────────────────────────────────────────────────────────

def _enrich_registration(reg, activity):
    """Attach product_name and component_name to each registration item."""
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


@router.get("/activities/{activity_id}/registrations", response_model=List[RegistrationResponse])
def get_registrations(
    activity_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return [_enrich_registration(r, activity) for r in activity.registrations]


# ── Excel-export per onderdeel (#85) ──────────────────────────────────────────

@router.get("/activities/{activity_id}/components/{component_id}/export")
def export_component_xlsx(
    activity_id: int,
    component_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Download een .xlsx met aantallen per product + financials voor één
    onderdeel, zoals ze nu in de DB staan (#85). Admin-only; bevat persoons- en
    financiële data."""
    import re

    activity = _load_activity_or_404(db, activity_id)
    component = db.query(ActivitySubRegistration).filter(
        ActivitySubRegistration.id == component_id,
        ActivitySubRegistration.activity_id == activity.id,
    ).first()
    if not component:
        raise HTTPException(status_code=404, detail="Component not found")

    content = build_component_export_xlsx(db, activity, component)
    raw_name = f"{activity.name}-{component.name}"
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", raw_name).strip("_") or "export"
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{safe}.xlsx"'},
    )


# ── Bestelregels bewerken (admin) + audit (#84) ───────────────────────────────

def _load_activity_or_404(db: Session, activity_id: int) -> Activity:
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return activity


def _load_registration_or_404(db: Session, activity: Activity, registration_id: int) -> Registration:
    reg = db.query(Registration).filter(
        Registration.id == registration_id,
        Registration.activity_id == activity.id,
    ).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Registration not found")
    return reg


def _validate_order_product(db: Session, activity: Activity, reg: Registration, product_id: int) -> ActivityProduct:
    """Een bestelregel mag enkel een product van dit onderdeel/deze activiteit bevatten."""
    product = db.query(ActivityProduct).filter(ActivityProduct.id == product_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    comp = db.query(ActivitySubRegistration).filter(
        ActivitySubRegistration.id == product.component_id
    ).first()
    if not comp or comp.activity_id != activity.id:
        raise HTTPException(status_code=400, detail="Product hoort niet bij deze activiteit.")
    if reg.component_id is not None and product.component_id != reg.component_id:
        raise HTTPException(status_code=400, detail="Product hoort niet bij het onderdeel van deze inschrijving.")
    return product


def _order_edit_result(db: Session, activity: Activity, reg: Registration) -> dict:
    """Vernieuwde bestelling + financiële stand; signaleert of er nu een
    terugbetaling openstaat (saldo < 0) zodat de UI naar de refund-flow kan wijzen."""
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
    activity = _load_activity_or_404(db, activity_id)
    reg = _load_registration_or_404(db, activity, registration_id)
    if data.quantity < 1:
        raise HTTPException(status_code=400, detail="Aantal moet minstens 1 zijn.")
    _validate_order_product(db, activity, reg, data.product_id)
    item = RegistrationItem(registration_id=reg.id, product_id=data.product_id, quantity=data.quantity)
    db.add(item)
    db.flush()
    snapshot_registration_item(
        db, item, operation="insert", action="order_changed",
        source="admin_manual", actor=admin.email,
    )
    db.commit()
    return _order_edit_result(db, activity, reg)


@router.patch("/activities/{activity_id}/registrations/{registration_id}/items/{item_id}")
def update_order_line(
    activity_id: int,
    registration_id: int,
    item_id: int,
    data: RegistrationItemUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    activity = _load_activity_or_404(db, activity_id)
    reg = _load_registration_or_404(db, activity, registration_id)
    item = db.query(RegistrationItem).filter(
        RegistrationItem.id == item_id,
        RegistrationItem.registration_id == reg.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Order line not found")
    if data.product_id is not None:
        _validate_order_product(db, activity, reg, data.product_id)
        item.product_id = data.product_id
    if data.quantity is not None:
        if data.quantity < 1:
            raise HTTPException(status_code=400, detail="Aantal moet minstens 1 zijn; verwijder de regel om ze te schrappen.")
        item.quantity = data.quantity
    db.flush()
    snapshot_registration_item(
        db, item, operation="update", action="order_changed",
        source="admin_manual", actor=admin.email,
    )
    db.commit()
    return _order_edit_result(db, activity, reg)


@router.delete("/activities/{activity_id}/registrations/{registration_id}/items/{item_id}")
def delete_order_line(
    activity_id: int,
    registration_id: int,
    item_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    activity = _load_activity_or_404(db, activity_id)
    reg = _load_registration_or_404(db, activity, registration_id)
    item = db.query(RegistrationItem).filter(
        RegistrationItem.id == item_id,
        RegistrationItem.registration_id == reg.id,
    ).first()
    if not item:
        raise HTTPException(status_code=404, detail="Order line not found")
    # Snapshot vóór de (soft) delete (#84/#166): de bronrij blijft bestaan maar
    # wordt gemarkeerd; de globale filter sluit ze uit bij de saldo-herberekening.
    snapshot_registration_item(
        db, item, operation="delete", action="order_changed",
        source="admin_manual", actor=admin.email,
    )
    soft_delete(item)
    db.commit()
    return _order_edit_result(db, activity, reg)


@router.get("/activities/{activity_id}/public-registrations")
def get_public_registrations(
    activity_id: int,
    component_id: int,
    db: Session = Depends(get_db),
):
    """Return public participant list for a given component."""
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

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
        raise HTTPException(status_code=404, detail="Activity not found")

    today = date.today()
    if not any(_is_future(d, today) for d in activity.dates):
        raise HTTPException(status_code=400, detail="Activity is no longer open for registration")

    if data.contact_email:
        existing_count = db.query(Registration).filter(
            Registration.activity_id == activity_id,
            Registration.component_id == data.component_id,
            func.lower(Registration.contact_email) == data.contact_email.lower(),
        ).count()
        if existing_count >= settings.max_registrations_per_email:
            raise HTTPException(
                status_code=409,
                detail=f"Er zijn al {settings.max_registrations_per_email} inschrijvingen met dit "
                       "e-mailadres voor dit onderdeel. Neem contact op met het bestuur als je er meer nodig hebt.",
            )

    valid_product_ids = {
        p.id for comp in activity.sub_registrations for p in comp.products
    }

    for item_data in data.items:
        if item_data.product_id not in valid_product_ids:
            raise HTTPException(
                status_code=400,
                detail="Ongeldig product in de inschrijving.",
            )
        if item_data.quantity < 0 or item_data.quantity > settings.max_item_quantity:
            raise HTTPException(
                status_code=400,
                detail=f"Ongeldig aantal: kies een waarde tussen 0 en {settings.max_item_quantity}.",
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
                    detail="Dit onderdeel is volzet. Inschrijven is niet meer mogelijk.",
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
    total_amount, _ = compute_registration_total(registration)

    checkout_url = None
    payment_record = None
    if data.payment_method and total_amount > 0:
        method = "online" if data.payment_method == "ONLINE" else "transfer"
        redirect_url = f"{settings.frontend_url}/betaling/succes?registration={registration.id}"
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
                from app.domains.payment_gateway.models import GatewayPayment
                gp = db.query(GatewayPayment).filter(GatewayPayment.id == payment_record.gateway_payment_id).first()
                if gp:
                    checkout_url = gp.checkout_url
        except Exception as e:
            logger.error("Betaling aanmaken mislukt voor inschrijving (%s): %s", method, e)
            if method == "online":
                db.rollback()
                raise HTTPException(
                    status_code=502,
                    detail="De online betaling kon niet gestart worden. Je inschrijving is niet bewaard — probeer ze later opnieuw.",
                )

        if method == "online" and not checkout_url:
            db.rollback()
            raise HTTPException(
                status_code=502,
                detail="De online betaling kon niet gestart worden. Je inschrijving is niet bewaard — probeer ze later opnieuw.",
            )

    # Business-event (#152): inschrijving voltooid. Geen PII — enkel niet-
    # identificerende context. Commit mee in dezelfde transactie.
    log_business_event(
        db, "inschrijving_voltooid",
        activity_id=activity_id,
        payment_record_id=payment_record.id if payment_record else None,
        payload={
            "form_type": getattr(activity, "reg_form_type", None),
            "paid": total_amount > 0,
            "amount": str(total_amount),
            "payment_method": data.payment_method,
        },
    )

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
