import logging
from datetime import date
from sqlalchemy import or_, and_
from typing import List

from fastapi import APIRouter, Depends, HTTPException

logger = logging.getLogger(__name__)
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models.activity import Activity, Registration, RegistrationItem
from app.models.user import User
from app.models.activity_sub_registration import ActivitySubRegistration, ActivityProduct
from app.schemas.activity import (
    ActivityCreate,
    ActivityUpdate,
    ActivityResponse,
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
from app.config import settings
from app.domains.payment_status.service import create_payment_record

router = APIRouter(tags=["activities"])


def compute_activity_status(activity: Activity) -> dict:
    registrations = [r for r in activity.registrations if not r.is_waitlist]
    waitlist = [r for r in activity.registrations if r.is_waitlist]
    count = len(registrations)
    wl_count = len(waitlist)

    end = activity.date_end or activity.date
    if end < date.today():
        status = "Voorbij"
    elif activity.is_cancelled:
        status = "Geannuleerd"
    elif wl_count > 0:
        status = "Wachtlijst"
    else:
        status = "Open"

    return {"status": status, "registration_count": count, "waitlist_count": wl_count}


# ── Activities ────────────────────────────────────────────────────────────────

@router.get("/activities", response_model=List[ActivityResponse])
def list_activities(db: Session = Depends(get_db)):
    today = date.today()
    still_running = or_(
        and_(Activity.date_end != None, Activity.date_end >= today),
        and_(Activity.date_end == None, Activity.date >= today),
    )
    activities = (
        db.query(Activity)
        .filter(still_running)
        .order_by(Activity.date.asc())
        .all()
    )
    result = []
    for a in activities:
        info = compute_activity_status(a)
        resp = ActivityResponse.model_validate(a)
        resp.status = info["status"]
        resp.registration_count = info["registration_count"]
        resp.waitlist_count = info["waitlist_count"]
        result.append(resp)
    return result


@router.get("/activities/archived", response_model=List[ActivityResponse])
def list_archived_activities(db: Session = Depends(get_db)):
    today = date.today()
    activities = (
        db.query(Activity)
        .filter(
            or_(
                and_(Activity.date_end == None, Activity.date < today),
                and_(Activity.date_end != None, Activity.date_end < today),
            )
        )
        .order_by(Activity.date.desc())
        .all()
    )
    result = []
    for a in activities:
        info = compute_activity_status(a)
        resp = ActivityResponse.model_validate(a)
        resp.status = info["status"]
        resp.registration_count = info["registration_count"]
        resp.waitlist_count = info["waitlist_count"]
        result.append(resp)
    return result


@router.post("/activities", response_model=ActivityResponse)
def create_activity(
    data: ActivityCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    activity = Activity(
        name=data.name,
        date=data.date,
        date_end=data.date_end,
        time=data.time,
        location=data.location,
        poster_url=data.poster_url,
    )
    db.add(activity)
    db.commit()
    db.refresh(activity)
    resp = ActivityResponse.model_validate(activity)
    resp.status = "Open"
    resp.registration_count = 0
    resp.waitlist_count = 0
    return resp


@router.put("/activities/{activity_id}", response_model=ActivityResponse)
def update_activity(
    activity_id: int,
    data: ActivityUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    for field, value in data.model_dump(exclude_none=True).items():
        setattr(activity, field, value)
    db.commit()
    db.refresh(activity)
    info = compute_activity_status(activity)
    resp = ActivityResponse.model_validate(activity)
    resp.status = info["status"]
    resp.registration_count = info["registration_count"]
    resp.waitlist_count = info["waitlist_count"]
    return resp


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


@router.post("/activities/{activity_id}/register", response_model=RegistrationResponse)
def register_for_activity(
    activity_id: int,
    data: RegistrationCreate,
    db: Session = Depends(get_db),
):
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    end = activity.date_end or activity.date
    if end < date.today():
        raise HTTPException(status_code=400, detail="Activity is no longer open for registration")

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

    # Compute total amount from items
    product_prices = {}
    for comp in activity.sub_registrations:
        for p in comp.products:
            product_prices[p.id] = p.price

    from decimal import Decimal
    total_amount = sum(
        product_prices.get(item.product_id, Decimal("0")) * item.quantity
        for item in data.items
        if item.quantity > 0 and not next(
            (p for comp in activity.sub_registrations for p in comp.products if p.id == item.product_id and p.is_free), None
        )
    )

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
            )
            if method == "online" and payment_record.gateway_payment_id:
                from app.domains.payment_gateway.models import GatewayPayment
                gp = db.query(GatewayPayment).filter(GatewayPayment.id == payment_record.gateway_payment_id).first()
                if gp:
                    checkout_url = gp.checkout_url
        except Exception:
            pass

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
                )
        except Exception as e:
            logger.error("Activiteit bevestigingsmail mislukt naar %s: %s", data.contact_email, e)

    result = _enrich_registration(registration, activity)
    result["checkout_url"] = checkout_url
    return result
