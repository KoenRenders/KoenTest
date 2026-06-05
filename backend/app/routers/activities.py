import json
from datetime import date, datetime
from decimal import Decimal
from sqlalchemy import or_, and_
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models.activity import Activity, Registration, RegistrationItem
from app.models.member import Membership
from app.models.user import User
from app.models.activity_sub_registration import ActivitySubRegistration
from app.schemas.activity import (
    ActivityCreate,
    ActivityUpdate,
    ActivityResponse,
    SubRegistrationResponse,
    RegistrationCreate,
    RegistrationResponse,
    PublicRegistrationSummary,
)
from app.services.email import send_waitlist_notification

router = APIRouter(tags=["activities"])


def compute_participant_count(registration: Registration) -> int:
    """Compute the effective participant count for a registration."""
    form_type = None
    # Try to determine form type from context
    # We'll use group_size/age_categories/items as heuristics
    if registration.group_size and registration.group_size > 1:
        return registration.group_size
    if registration.age_categories:
        try:
            cats = json.loads(registration.age_categories)
            if isinstance(cats, dict):
                total = sum(int(v) for v in cats.values() if v)
                if total > 0:
                    return total
        except Exception:
            pass
    if registration.items:
        total = sum(item.quantity for item in registration.items)
        if total > 0:
            return total
    return 1


def compute_activity_status(activity: Activity) -> dict:
    registrations = [r for r in activity.registrations if not r.is_waitlist]
    waitlist = [r for r in activity.registrations if r.is_waitlist]
    count = len(registrations)
    wl_count = len(waitlist)

    # Compute total participants accounting for group sizes
    total_participants = sum(compute_participant_count(r) for r in registrations)

    end = activity.date_end or activity.date
    if end < date.today():
        status = "Voorbij"
    elif activity.is_cancelled:
        status = "Geannuleerd"
    elif activity.max_participants and total_participants >= activity.max_participants:
        status = "Vol"
    elif wl_count > 0:
        status = "Wachtlijst"
    else:
        status = "Open"

    return {
        "status": status,
        "registration_count": count,
        "waitlist_count": wl_count,
    }


@router.get("/activities", response_model=List[ActivityResponse])
def list_activities(db: Session = Depends(get_db)):
    today = date.today()
    still_running = or_(
        and_(Activity.date_end != None, Activity.date_end >= today),
        and_(Activity.date_end == None, Activity.date >= today),
    )
    activities = (
        db.query(Activity)
        .filter(Activity.is_archived == False, still_running)
        .order_by(Activity.date.asc())
        .all()
    )
    result = []
    for activity in activities:
        info = compute_activity_status(activity)
        resp = ActivityResponse.model_validate(activity)
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
            (Activity.is_archived == True) |
            and_(Activity.date_end == None, Activity.date < today) |
            and_(Activity.date_end != None, Activity.date_end < today)
        )
        .order_by(Activity.date.desc())
        .all()
    )
    result = []
    for activity in activities:
        info = compute_activity_status(activity)
        resp = ActivityResponse.model_validate(activity)
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
        time=data.time,
        location=data.location,
        max_participants=data.max_participants,
        registration_type_code=data.registration_type_code,
        price=data.price,
        member_price=data.member_price,
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
    return {"detail": "Activity deleted"}


@router.get("/activities/{activity_id}/registrations/public", response_model=PublicRegistrationSummary)
def get_public_registrations(
    activity_id: int,
    db: Session = Depends(get_db),
):
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    active_regs = [r for r in activity.registrations if not r.is_waitlist]
    names = [r.contact_name or "Anoniem" for r in active_regs]
    total_participants = sum(compute_participant_count(r) for r in active_regs)

    return PublicRegistrationSummary(
        names=names,
        total_registrations=len(active_regs),
        total_participants=total_participants,
    )


@router.get("/activities/{activity_id}/registrations", response_model=List[RegistrationResponse])
def get_registrations(
    activity_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")
    return [r for r in activity.registrations if not r.is_waitlist]


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


@router.post("/activities/{activity_id}/register", response_model=RegistrationResponse)
def register_for_activity(
    activity_id: int,
    data: RegistrationCreate,
    db: Session = Depends(get_db),
):
    activity = db.query(Activity).filter(Activity.id == activity_id).first()
    if not activity:
        raise HTTPException(status_code=404, detail="Activity not found")

    today = date.today()
    if activity.date < today or activity.is_archived:
        raise HTTPException(status_code=400, detail="Activity is no longer open for registration")

    # Determine effective participant count for capacity check
    participant_count = 1
    form_type = activity.reg_form_type or "NONE"

    if data.sub_registration_id:
        sub = db.query(ActivitySubRegistration).filter(
            ActivitySubRegistration.id == data.sub_registration_id
        ).first()
        if sub and sub.reg_form_type:
            form_type = sub.reg_form_type

    if form_type in ("GROUP", "PAID_PER_PERSON"):
        participant_count = data.group_size or 1
    elif form_type == "AGE_CATEGORY" and data.age_categories:
        try:
            cats = json.loads(data.age_categories)
            if isinstance(cats, dict):
                participant_count = sum(int(v) for v in cats.values() if v) or 1
        except Exception:
            participant_count = 1
    elif form_type == "PAID_PRODUCTS" and data.items:
        participant_count = sum(item.quantity for item in data.items) or 1

    # Check capacity
    current_registrations = [r for r in activity.registrations if not r.is_waitlist]
    current_participants = sum(compute_participant_count(r) for r in current_registrations)
    is_full = activity.max_participants and (current_participants + participant_count) > activity.max_participants
    is_waitlist = bool(is_full)

    # Determine payment status
    payment_method = data.payment_method or "FREE"
    is_free = float(activity.price or 0) == 0 and form_type not in ("PAID_PRODUCTS", "PAID_PER_PERSON")
    if is_free or payment_method == "FREE":
        payment_status = "FREE"
    elif payment_method in ("CASH", "TRANSFER"):
        payment_status = "PAID"
    else:
        payment_status = "PENDING"

    registration = Registration(
        activity_id=activity_id,
        person_id=None,
        is_waitlist=is_waitlist,
        registration_type="INDIVIDUAL",
        contact_name=data.contact_name,
        contact_email=data.contact_email,
        contact_phone=data.contact_phone,
        team_name=data.team_name,
        group_size=data.group_size,
        age_categories=data.age_categories,
        remarks=data.remarks,
        payment_method=payment_method,
        payment_status=payment_status,
        sub_registration_id=data.sub_registration_id,
    )
    db.add(registration)
    db.flush()

    # Create RegistrationItem records for PAID_PRODUCTS
    for item_data in data.items:
        sub = db.query(ActivitySubRegistration).filter(
            ActivitySubRegistration.id == item_data.sub_registration_id
        ).first()
        if sub:
            unit_price = sub.price or Decimal("0.00")
            reg_item = RegistrationItem(
                registration_id=registration.id,
                sub_registration_id=item_data.sub_registration_id,
                quantity=item_data.quantity,
                unit_price=unit_price,
                created_at=datetime.utcnow(),
                updated_at=datetime.utcnow(),
            )
            db.add(reg_item)

    db.commit()
    db.refresh(registration)

    # Send notification email if on waitlist
    if is_waitlist and data.contact_email:
        try:
            send_waitlist_notification(
                to_email=data.contact_email,
                name=data.contact_name or "Deelnemer",
                activity_name=activity.name,
            )
        except Exception:
            pass

    return registration
