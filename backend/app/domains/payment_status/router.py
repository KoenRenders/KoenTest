from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.auth import get_current_admin
from app.database import get_db
from app.models.user import User
from .models import PaymentRecord
from .schemas import PaymentRecordResponse, PaymentRecordUpdate, EnrichedPaymentRecord
from .service import confirm_manual_payment, get_records_for, handle_gateway_update
from app.domains.audit.service import snapshot_payment_record

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
        reg_items: list = []

        if r.payable_type == "registration":
            reg = db.query(Registration).filter(Registration.id == r.payable_id).first()
            if reg:
                contact_name = reg.contact_name
                activity_id = reg.activity_id
                activity = db.query(Activity).filter(Activity.id == reg.activity_id).first()
                if activity:
                    description = activity.name
                    product_map = {p.id: p for comp in activity.sub_registrations for p in comp.products}
                    for item in reg.items:
                        p = product_map.get(item.product_id)
                        reg_items.append({
                            "product_name": p.name if p else f"product {item.product_id}",
                            "quantity": item.quantity,
                            "unit_price": float(p.price) if p else 0,
                            "subtotal": float(p.price) * item.quantity if p else 0,
                        })
        elif r.payable_type == "membership":
            member = db.query(Member).filter(Member.id == r.payable_id).first()
            if member:
                description = "Lidmaatschap"
                # get hoofdlid name
                mp = db.query(MemberPerson).filter(
                    MemberPerson.member_id == member.id,
                    MemberPerson.relation_type == "HOOFDLID",
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
            items=reg_items,
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


@router.post("/records/{record_id}/refresh", response_model=PaymentRecordResponse)
def refresh_payment_record(
    record_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Haal de actuele status bij de gateway (Mollie) op voor één betaling.

    Vangnet voor de zeldzame gemiste webhook: de webhook blijft het primaire
    pad, maar hiermee kan een admin de waarheid bij Mollie opvragen en de
    PaymentRecord bijwerken. Werkt enkel voor online betalingen.
    """
    record = db.query(PaymentRecord).filter(PaymentRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Payment record not found")
    if record.method != "online" or not record.gateway_payment_id:
        raise HTTPException(
            status_code=400,
            detail="Alleen online betalingen kunnen bij Mollie ververst worden.",
        )

    from app.domains.payment_gateway.service import refresh_payment_status

    gp = refresh_payment_status(db, record.gateway_payment_id)
    handle_gateway_update(
        db, gateway_payment_id=gp.id, new_status=gp.status,
        source="admin_refresh", actor=admin.email,
    )
    db.commit()
    db.refresh(record)
    return _to_response(record)


@router.patch("/records/{record_id}", response_model=PaymentRecordResponse)
def update_payment_record(
    record_id: str,
    data: PaymentRecordUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    record = db.query(PaymentRecord).filter(PaymentRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Payment record not found")

    if data.amount_paid is not None:
        if data.amount_paid < 0:
            raise HTTPException(status_code=400, detail="amount_paid mag niet negatief zijn")
        if data.amount_paid > record.amount:
            raise HTTPException(
                status_code=400,
                detail=f"amount_paid ({data.amount_paid}) mag het verschuldigde bedrag ({record.amount}) niet overschrijden",
            )

    if data.status == "paid":
        confirm_manual_payment(db, record_id, data.note, actor=admin.email)
        if data.amount_paid is not None:
            record.amount_paid = data.amount_paid
    else:
        if data.status is not None:
            record.status = data.status
        if data.note is not None:
            record.note = data.note
        if data.amount_paid is not None:
            record.amount_paid = data.amount_paid
        snapshot_payment_record(
            db, record,
            operation="update", action="payment_updated",
            source="admin_update", actor=admin.email,
        )

    db.commit()
    db.refresh(record)
    return _to_response(record)
