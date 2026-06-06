from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from sqlalchemy.orm import Session
from .models import PaymentRecord
from .schemas import MEMBERSHIP_PRICE_FULL, MEMBERSHIP_PRICE_HALF


def membership_price_for_date(today: Optional[date] = None) -> Decimal:
    """Half price from April 16 to September 16 (inclusive)."""
    if today is None:
        today = date.today()
    half_start = date(today.year, 4, 16)
    half_end = date(today.year, 9, 16)
    if half_start <= today <= half_end:
        return MEMBERSHIP_PRICE_HALF
    return MEMBERSHIP_PRICE_FULL


def create_payment_record(
    db: Session,
    payable_type: str,
    payable_id: int,
    amount: Decimal,
    method: str,
    redirect_url: Optional[str] = None,
    description: Optional[str] = None,
) -> PaymentRecord:
    if method == "online":
        from app.domains.payment_gateway.service import create_payment as gw_create
        gp = gw_create(
            db=db,
            amount=amount,
            description=description or f"{payable_type} #{payable_id}",
            redirect_url=redirect_url or "",
            metadata={"payable_type": payable_type, "payable_id": payable_id},
        )
        record = PaymentRecord(
            payable_type=payable_type,
            payable_id=payable_id,
            amount=amount,
            method=method,
            status=gp.status,
            gateway_payment_id=gp.id,
        )
    else:
        record = PaymentRecord(
            payable_type=payable_type,
            payable_id=payable_id,
            amount=amount,
            method=method,
            status="pending",
        )

    db.add(record)
    db.flush()
    return record


def handle_gateway_update(db: Session, gateway_payment_id: str, new_status: str) -> None:
    """Called by gateway webhook handler to propagate status to PaymentRecord."""
    records = db.query(PaymentRecord).filter(
        PaymentRecord.gateway_payment_id == gateway_payment_id
    ).all()
    for record in records:
        record.status = new_status
        if new_status == "paid" and record.paid_at is None:
            record.paid_at = datetime.utcnow()


def confirm_manual_payment(
    db: Session,
    record_id: str,
    note: Optional[str] = None,
) -> PaymentRecord:
    record = db.query(PaymentRecord).filter(PaymentRecord.id == record_id).first()
    if not record:
        raise ValueError(f"PaymentRecord {record_id} not found")
    record.status = "paid"
    record.paid_at = datetime.utcnow()
    if note:
        record.note = note
    db.flush()
    return record


def get_records_for(db: Session, payable_type: str, payable_id: int) -> list[PaymentRecord]:
    return db.query(PaymentRecord).filter(
        PaymentRecord.payable_type == payable_type,
        PaymentRecord.payable_id == payable_id,
    ).all()
