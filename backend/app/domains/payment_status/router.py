from datetime import datetime, timezone
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.auth import get_current_admin
from app.database import get_db
from app.models.user import User
from .models import PaymentRecord
from .schemas import (
    PaymentRecordResponse, PaymentRecordUpdate, EnrichedPaymentRecord,
    RefundCreate, RegistrationBalance,
)
from .service import (
    confirm_manual_payment, get_records_for, handle_gateway_update,
    create_refund, registration_balance,
)
from app.domains.audit.service import snapshot_payment_record
from app.soft_delete import soft_delete
from app.services.registration_totals import compute_registration_total

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
        type=r.type,
        refund_of_id=r.refund_of_id,
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
    from app.models.activity_sub_registration import ActivitySubRegistration
    from app.models.member import Member, MemberPerson, Person

    records = db.query(PaymentRecord).order_by(PaymentRecord.created_at.desc()).all()
    result = []
    for r in records:
        contact_name: Optional[str] = None
        description: Optional[str] = None
        activity_id: Optional[int] = None
        component_id: Optional[int] = None
        component_name: Optional[str] = None
        reg_items: list = []

        if r.payable_type == "registration":
            reg = db.query(Registration).filter(Registration.id == r.payable_id).first()
            if reg:
                contact_name = reg.contact_name
                activity_id = reg.activity_id
                component_id = reg.component_id
                if reg.component_id is not None:
                    comp = db.query(ActivitySubRegistration).filter(
                        ActivitySubRegistration.id == reg.component_id
                    ).first()
                    component_name = comp.name if comp else None
                activity = db.query(Activity).filter(Activity.id == reg.activity_id).first()
                if activity:
                    description = activity.name
                    _total, regels = compute_registration_total(reg)
                    reg_items = [
                        {
                            "product_name": line["name"],
                            "quantity": line["quantity"],
                            "unit_price": float(line["unit_price"]),
                            "subtotal": float(line["subtotal"]),
                        }
                        for line in regels
                    ]
        elif r.payable_type == "membership":
            # payable_id is de Membership.id (niet de Member.id) — eerst het
            # lidmaatschap ophalen voor het jaar, dan het gezin + hoofdlid (#141).
            from app.models.member import Membership
            ms = db.query(Membership).filter(Membership.id == r.payable_id).first()
            description = f"Lidmaatschap {ms.year}" if ms else "Lidmaatschap"
            if ms:
                member = db.query(Member).filter(Member.id == ms.member_id).first()
                if member:
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
            component_id=component_id,
            component_name=component_name,
            items=reg_items,
            amount=r.amount,
            amount_paid=r.amount_paid,
            method=r.method,
            status=r.status,
            type=r.type,
            refund_of_id=r.refund_of_id,
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


@router.post("/records/{record_id}/refund", response_model=PaymentRecordResponse)
def refund_payment_record(
    record_id: str,
    data: RefundCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Registreer een terugbetaling op een charge-record (#83).

    Maakt een apart, negatief PaymentRecord (``type="refund"``) dat naar de
    charge verwijst. De financiële invarianten zitten in de service-laag.
    """
    try:
        refund = create_refund(
            db, record_id, data.amount,
            note=data.note, method=data.method, actor=admin.email,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    db.refresh(refund)
    return _to_response(refund)


@router.get("/registrations/{registration_id}/balance", response_model=RegistrationBalance)
def get_registration_balance(
    registration_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    """Financiële stand van een inschrijving: verschuldigd, betaald, terugbetaald,
    saldo (#83). De live DB is de bron van waarheid."""
    from app.models.activity import Registration

    reg = db.query(Registration).filter(Registration.id == registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail="Registration not found")
    return RegistrationBalance(**registration_balance(db, reg))


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
        confirm_manual_payment(db, record_id, data.note, actor=admin.email, amount_paid=data.amount_paid)
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


@router.delete("/records/{record_id}", status_code=204)
def delete_payment_record(
    record_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    """Verwijder één betaalrecord als bewuste admin-actie (#167) — bv. een
    foutieve/test-betaling of een weesbetaling na een gezin-delete. Soft delete
    (#166): de rij wordt gemarkeerd (deleted_at) en globaal uit reads gefilterd,
    met audit-snapshot zodat het financiële feit in de history bewaard blijft."""
    record = db.query(PaymentRecord).filter(PaymentRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Payment record not found")
    snapshot_payment_record(
        db, record,
        operation="delete", action="payment_deleted",
        source="admin_manual", actor=admin.email,
    )
    soft_delete(record)
    db.commit()
