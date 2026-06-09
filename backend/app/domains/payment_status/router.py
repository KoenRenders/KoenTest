from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.auth import get_current_admin
from app.database import get_db
from app.models.user import User
from .models import PaymentRecord
from .schemas import PaymentRecordResponse, PaymentRecordUpdate
from .service import confirm_manual_payment, get_records_for

router = APIRouter(prefix="/payment-status", tags=["payment-status"])


@router.get("/records/{payable_type}/{payable_id}", response_model=List[PaymentRecordResponse])
def get_payment_records(
    payable_type: str,
    payable_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    records = get_records_for(db, payable_type, payable_id)
    result = []
    for r in records:
        resp = PaymentRecordResponse(
            id=r.id,
            payable_type=r.payable_type,
            payable_id=r.payable_id,
            amount=r.amount,
            method=r.method,
            status=r.status,
            note=r.note,
            paid_at=r.paid_at,
            checkout_url=r.gateway_payment.checkout_url if r.gateway_payment else None,
            created_at=r.created_at,
        )
        result.append(resp)
    return result


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
    else:
        record.status = data.status
        if data.note:
            record.note = data.note

    db.commit()
    db.refresh(record)
    return PaymentRecordResponse(
        id=record.id,
        payable_type=record.payable_type,
        payable_id=record.payable_id,
        amount=record.amount,
        method=record.method,
        status=record.status,
        note=record.note,
        paid_at=record.paid_at,
        checkout_url=record.gateway_payment.checkout_url if record.gateway_payment else None,
        created_at=record.created_at,
    )
