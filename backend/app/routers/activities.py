from datetime import date
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models.activity import Activity, Registration
from app.models.member import Membership
from app.models.user import User
from app.schemas.activity import (
    ActivityCreate,
    ActivityUpdate,
    ActivityResponse,
    RegistrationCreate,
    RegistrationResponse,
)
from app.services.email import send_waitlist_notification

router = APIRouter(tags=["activities"])


def compute_activity_status(activity: Activity) -> dict:
    registrations = [r for r in activity.registrations if not r.is_waitlist]
    waitlist = [r for r in activity.registrations if r.is_waitlist]
    count = len(registrations)
    wl_count = len(waitlist)

    if activity.max_participants and count >= activity.max_participants:
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
    activities = (
        db.query(Activity)
        .filter(Activity.is_archived == False, Activity.date >= today)
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
        .filter((Activity.is_archived == True) | (Activity.date < today))
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

    # Check capacity
    current_registrations = [r for r in activity.registrations if not r.is_waitlist]
    is_full = activity.max_participants and len(current_registrations) >= activity.max_participants
    is_waitlist = bool(is_full)

    registration = Registration(
        activity_id=activity_id,
        person_id=data.person_id,
        is_waitlist=is_waitlist,
        registration_type=data.registration_type_code,
        contact_name=data.contact_name,
        contact_email=data.contact_email,
    )
    db.add(registration)
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
