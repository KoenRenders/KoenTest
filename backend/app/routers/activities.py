import logging
from datetime import date
from sqlalchemy import or_, and_, func
from typing import List

from fastapi import APIRouter, Depends, HTTPException

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
)
from app.services.email import send_waitlist_notification, send_activity_registration_confirmation
from app.services.registration_totals import compute_registration_total
from app.config import settings
from app.domains.payment_status.service import create_payment_record
from app.limiter import registration_limiter

router = APIRouter(tags=["activities"])


def _effective_end(ad: ActivityDate) -> date:
    return ad.end_date or ad.start_date


def _is_future(ad: ActivityDate, today: date) -> bool:
    return _effective_end(ad) >= today


def compute_activity_status(
    activity: Activity,
    registration_count: int | None = None,
    waitlist_count: int | None = None,
) -> dict:
    if registration_count is None or waitlist_count is None:
        registration_count = sum(1 for r in activity.registrations if not r.is_waitlist)
        waitlist_count = sum(1 for r in activity.registrations if r.is_waitlist)

    today = date.today()
    all_past = not any(_is_future(d, today) for d in activity.dates)

    if all_past or not activity.dates:
        status = "Voorbij"
    elif activity.is_cancelled:
        status = "Geannuleerd"
    elif waitlist_count > 0:
        status = "Wachtlijst"
    else:
        status = "Open"

    return {
        "status": status,
        "registration_count": registration_count,
        "waitlist_count": waitlist_count,
    }


def _registration_counts(db: Session, activity_ids: List[int]) -> dict:
    """Tellingen (regulier, wachtlijst) per activiteit in één GROUP BY-query."""
    counts: dict = {aid: [0, 0] for aid in activity_ids}
    if not activity_ids:
        return counts
    rows = (
        db.query(Registration.activity_id, Registration.is_waitlist, func.count())
        .filter(Registration.activity_id.in_(activity_ids))
        .group_by(Registration.activity_id, Registration.is_waitlist)
        .all()
    )
    for activity_id, is_waitlist, cnt in rows:
        counts.setdefault(activity_id, [0, 0])[1 if is_waitlist else 0] = cnt
    return counts


def _build_response(
    activity: Activity,
    today: date,
    for_archive: bool = False,
    all_dates: bool = False,
    reg_count: int = 0,
    wl_count: int = 0,
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
    resp.waitlist_count = wl_count
    return resp


# ── Activities ────────────────────────────────────────────────────────────────

@router.get("/activities", response_model=List[ActivityResponse])
def list_activities(include_all_dates: bool = False, db: Session = Depends(get_db)):
    today = date.today()
    effective_end = func.coalesce(ActivityDate.end_date, ActivityDate.start_date)

    has_future = (
        db.query(ActivityDate.id)
        .filter(
            ActivityDate.activity_id == Activity.id,
            effective_end >= today,
        )
        .correlate(Activity)
        .exists()
    )

    sort_date_sq = (
        db.query(func.min(ActivityDate.start_date))
        .filter(
            ActivityDate.activity_id == Activity.id,
            effective_end >= today,
        )
        .correlate(Activity)
        .scalar_subquery()
    )

    activities = (
        db.query(Activity)
        .options(
            selectinload(Activity.dates),
            selectinload(Activity.sub_registrations).selectinload(ActivitySubRegistration.products),
        )
        .filter(has_future)
        .order_by(sort_date_sq.asc())
        .all()
    )

    counts = _registration_counts(db, [a.id for a in activities])
    result = []
    for a in activities:
        reg_count, wl_count = counts.get(a.id, (0, 0))
        info = compute_activity_status(a, reg_count, wl_count)
        result.append(_build_response(a, today, all_dates=include_all_dates, reg_count=info["registration_count"], wl_count=info["waitlist_count"], status=info["status"]))
    return result


@router.get("/activities/archived", response_model=List[ActivityResponse])
def list_archived_activities(include_all_dates: bool = False, db: Session = Depends(get_db)):
    today = date.today()
    effective_end = func.coalesce(ActivityDate.end_date, ActivityDate.start_date)

    has_past = (
        db.query(ActivityDate.id)
        .filter(
            ActivityDate.activity_id == Activity.id,
            effective_end < today,
        )
        .correlate(Activity)
        .exists()
    )

    # Sorteer op de meest recente voorbije datum.
    sort_date_sq = (
        db.query(func.max(ActivityDate.start_date))
        .filter(
            ActivityDate.activity_id == Activity.id,
            effective_end < today,
        )
        .correlate(Activity)
        .scalar_subquery()
    )

    activities = (
        db.query(Activity)
        .options(
            selectinload(Activity.dates),
            selectinload(Activity.sub_registrations).selectinload(ActivitySubRegistration.products),
        )
        .filter(has_past)
        .order_by(sort_date_sq.desc())
        .all()
    )

    counts = _registration_counts(db, [a.id for a in activities])
    result = []
    for a in activities:
        reg_count, wl_count = counts.get(a.id, (0, 0))
        # Archiefkaarten tonen enkel voorbije datums → status is altijd "Voorbij"
        # (of "Geannuleerd"), ook als de activiteit nog toekomstige datums heeft.
        status = "Geannuleerd" if a.is_cancelled else "Voorbij"
        result.append(_build_response(a, today, for_archive=True, all_dates=include_all_dates, reg_count=reg_count, wl_count=wl_count, status=status))
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
    resp = _build_response(activity, today, status="Open", reg_count=0, wl_count=0)
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
    return _build_response(activity, today, status=info["status"], reg_count=info["registration_count"], wl_count=info["waitlist_count"])


@router.delete("/activities/{activity_id}")
def delete_activity(
    activity_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    db.delete(activity)
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
    db.delete(ad)
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
    db.delete(component)
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
    db.delete(product)
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
        "is_waitlist": reg.is_waitlist,
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
    return [_enrich_registration(r, activity) for r in activity.registrations if not r.is_waitlist]


@router.get("/activities/{activity_id}/waitlist", response_model=List[RegistrationResponse])
def get_waitlist(
    activity_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return [r for r in activity.registrations if r.is_waitlist]


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
        if reg.is_waitlist:
            continue
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
            func.lower(Registration.contact_email) == data.contact_email.lower(),
        ).count()
        if existing_count >= settings.max_registrations_per_email:
            raise HTTPException(
                status_code=409,
                detail=f"Er zijn al {settings.max_registrations_per_email} inschrijvingen voor deze "
                       "activiteit met dit e-mailadres. Neem contact op met het bestuur als je er meer nodig hebt.",
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
                if reg.is_waitlist or reg.component_id != data.component_id:
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
        is_waitlist=False,
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
            db.add(RegistrationItem(
                registration_id=registration.id,
                product_id=item_data.product_id,
                quantity=item_data.quantity,
            ))

    db.flush()
    db.refresh(registration)
    total_amount, _ = compute_registration_total(registration)

    checkout_url = None
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

    db.commit()
    db.refresh(registration)

    if data.contact_email:
        try:
            if registration.is_waitlist:
                send_waitlist_notification(
                    to_email=data.contact_email,
                    name=data.contact_name or "Deelnemer",
                    activity_name=activity.name,
                )
            else:
                send_activity_registration_confirmation(
                    to_email=data.contact_email,
                    name=data.contact_name or "Deelnemer",
                    activity=activity,
                    registration=registration,
                )
        except Exception as e:
            logger.error("Activiteit bevestigingsmail mislukt naar %s: %s", data.contact_email, e)

    result = _enrich_registration(registration, activity)
    result["checkout_url"] = checkout_url
    return result
