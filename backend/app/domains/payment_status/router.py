from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.auth import get_current_admin
from app.database import get_db
from app.models.user import User
from .models import PaymentRecord
from .schemas import PaymentRecordResponse, PaymentRecordUpdate, EnrichedPaymentRecord
from .service import confirm_manual_payment, get_records_for

router = APIRouter(prefix="/payment-status", tags=["payment-status"])


def _to_response(r: PaymentRecord) -> PaymentRecordResponse:
    return PaymentRecordResponse(
        id=r.id,
        payable_type=r.payable_type,
        payable_id=r.payable_id,
        amount=r.amount,
        amount_paid=r.amount_paid,
        method=r.method,
        status=r.status,
        note=r.note,
        paid_at=r.paid_at,
        checkout_url=r.gateway_payment.checkout_url if r.gateway_payment else None,
        created_at=r.created_at,
    )


@router.get("/records", response_model=List[EnrichedPaymentRecord])
def list_all_payment_records(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """List all payment records, enriched with contact name and description."""
    from app.models.activity import Registration, Activity
    from app.models.member import Member, MemberPerson, Person

    records = db.query(PaymentRecord).order_by(PaymentRecord.created_at.desc()).all()
    result = []
    for r in records:
        contact_name: Optional[str] = None
        description: Optional[str] = None
        activity_id: Optional[int] = None

        if r.payable_type == "registration":
            reg = db.query(Registration).filter(Registration.id == r.payable_id).first()
            if reg:
                contact_name = reg.contact_name
                activity_id = reg.activity_id
                activity = db.query(Activity).filter(Activity.id == reg.activity_id).first()
                if activity:
                    description = activity.name
        elif r.payable_type == "membership":
            member = db.query(Member).filter(Member.id == r.payable_id).first()
            if member:
                description = "Lidmaatschap"
                # get hoofdlid name
                mp = db.query(MemberPerson).filter(
                    MemberPerson.member_id == member.id,
                    MemberPerson.relation_type == "hoofdlid",
                ).first()
                if mp:
                    person = db.query(Person).filter(Person.id == mp.person_id).first()
                    if person:
                        contact_name = f"{person.first_name} {person.last_name}"

        result.append(EnrichedPaymentRecord(
            id=r.id,
            payable_type=r.payable_type,
            payable_id=r.payable_id,
            activity_id=activity_id,
            amount=r.amount,
            amount_paid=r.amount_paid,
            method=r.method,
            status=r.status,
            note=r.note,
            paid_at=r.paid_at,
            checkout_url=r.gateway_payment.checkout_url if r.gateway_payment else None,
            created_at=r.created_at,
            description=description,
            contact_name=contact_name,
        ))
    return result


@router.get("/records/{payable_type}/{payable_id}", response_model=List[PaymentRecordResponse])
def get_payment_records(
    payable_type: str,
    payable_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    records = get_records_for(db, payable_type, payable_id)
    return [_to_response(r) for r in records]


@router.patch("/records/{record_id}", response_model=PaymentRecordResponse)
def update_payment_record(
    record_id: str,
    data: PaymentRecordUpdate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    record = db.query(PaymentRecord).filter(PaymentRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Payment record not found")

    if data.status == "paid":
        confirm_manual_payment(db, record_id, data.note)
        if data.amount_paid is not None:
            record.amount_paid = data.amount_paid
    else:
        if data.status is not None:
            record.status = data.status
        if data.note is not None:
            record.note = data.note
        if data.amount_paid is not None:
            record.amount_paid = data.amount_paid

    db.commit()
    db.refresh(record)
    return _to_response(record)
