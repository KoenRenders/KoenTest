from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session
from app.domains.auth.api import get_finance_or_admin, get_current_finance
from app.database import get_db
from app.domains.auth.api import User
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
        structured_communication=r.structured_communication,
        created_at=r.created_at,
    )


@router.get("/records", response_model=List[EnrichedPaymentRecord])
def list_all_payment_records(
    db: Session = Depends(get_db),
    _viewer: User = Depends(get_finance_or_admin),
):
    """List all payment records, enriched with contact name and description.

    De betaling-records zelf volgen de gewone soft-delete-filter (verwijderde
    betalingen tonen niet), maar de **verrijking** (naam/activiteit/onderdeel) haalt
    bewust ook soft-deleted entiteiten op (`include_deleted=True`, #190): een betaling
    is een financieel feit en moet de (bewaarde) naam blijven tonen, niet "—"."""
    from app.models.activity import Registration, Activity
    from app.models.activity_sub_registration import ActivitySubRegistration
    from app.domains.mdm.api import Member, MemberPerson, Person

    def _q(model):
        return db.query(model).execution_options(include_deleted=True)

    records = db.query(PaymentRecord).order_by(PaymentRecord.created_at.desc()).all()
    result = []
    for r in records:
        contact_name: Optional[str] = None
        description: Optional[str] = None
        activity_id: Optional[int] = None
        component_id: Optional[int] = None
        component_name: Optional[str] = None
        membership_year: Optional[int] = None
        reg_items: list = []

        if r.payable_type == "registration":
            reg = _q(Registration).filter(Registration.id == r.payable_id).first()
            if reg:
                contact_name = reg.contact_name
                activity_id = reg.activity_id
                component_id = reg.component_id
                if reg.component_id is not None:
                    comp = _q(ActivitySubRegistration).filter(
                        ActivitySubRegistration.id == reg.component_id
                    ).first()
                    component_name = comp.name if comp else None
                activity = _q(Activity).filter(Activity.id == reg.activity_id).first()
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
            from app.domains.membership.api import Membership
            ms = _q(Membership).filter(Membership.id == r.payable_id).first()
            description = f"Lidmaatschap {ms.year}" if ms else "Lidmaatschap"
            membership_year = ms.year if ms else None
            if ms:
                member = _q(Member).filter(Member.id == ms.member_id).first()
                if member:
                    mp = _q(MemberPerson).filter(
                        MemberPerson.member_id == member.id,
                        MemberPerson.relation_type == "HOOFDLID",
                    ).first()
                    if mp:
                        person = _q(Person).filter(Person.id == mp.person_id).first()
                        if person:
                            contact_name = f"{person.first_name} {person.last_name}"

        result.append(EnrichedPaymentRecord(
            id=r.id,
            payable_type=r.payable_type,
            payable_id=r.payable_id,
            activity_id=activity_id,
            component_id=component_id,
            component_name=component_name,
            membership_year=membership_year,
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
            structured_communication=r.structured_communication,
            created_at=r.created_at,
            description=description,
            contact_name=contact_name,
        ))
    return result


@router.get("/records/export")
def export_all_payment_records(
    context: str = "all",
    status: str = "all",
    db: Session = Depends(get_db),
    _viewer: User = Depends(get_finance_or_admin),
):
    """Download de betalingen & vorderingen als .ods (#307): één blad met de
    zichtbare details + een totaalrij te betalen / betaald / saldo. Volgt het
    actieve filter van de pagina (context #90/#308 + status #83)."""
    from app.services.payments_export import build_payments_export_ods
    content = build_payments_export_ods(db, context=context, status=status)
    return Response(
        content=content,
        media_type="application/vnd.oasis.opendocument.spreadsheet",
        headers={"Content-Disposition": 'attachment; filename="betalingen-en-vorderingen.ods"'},
    )


@router.get("/records/{payable_type}/{payable_id}", response_model=List[PaymentRecordResponse])
def get_payment_records(
    payable_type: str,
    payable_id: int,
    db: Session = Depends(get_db),
    _viewer: User = Depends(get_finance_or_admin),
):
    records = get_records_for(db, payable_type, payable_id)
    return [_to_response(r) for r in records]


@router.post("/records/{record_id}/refresh", response_model=PaymentRecordResponse)
def refresh_payment_record(
    record_id: str,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_finance),
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

    from app.domains.payment.gateway_service import refresh_payment_status

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
    admin: User = Depends(get_current_finance),
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
    _viewer: User = Depends(get_finance_or_admin),
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
    admin: User = Depends(get_current_finance),
):
    record = db.query(PaymentRecord).filter(PaymentRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Payment record not found")

    if data.amount_paid is not None:
        # Tekengevoelige grens (#219): een charge heeft een positief bedrag → betaald
        # bedrag in [0, amount]; een refund is negatief → betaald bedrag in [amount, 0].
        lo, hi = sorted((Decimal("0"), Decimal(str(record.amount))))
        if not (lo <= data.amount_paid <= hi):
            raise HTTPException(
                status_code=400,
                detail=f"Betaald bedrag ({data.amount_paid}) moet tussen {lo} en {hi} liggen.",
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
            # Consistentie (#346): een ontvangen/terugbetaald bedrag (≠ 0) krijgt
            # meteen een paid_at, zodat er nooit een "betaald zonder datum"-record
            # ontstaat dat wél in totalen maar niet in datum-vensters meetelt.
            if data.amount_paid != 0 and record.paid_at is None:
                record.paid_at = datetime.now(timezone.utc)
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
    admin: User = Depends(get_current_finance),
):
    """Verwijder één betaalrecord als bewuste admin-actie (#167) — bv. een
    foutieve/test-betaling of een weesbetaling na een gezin-delete. Soft delete
    (#166): de rij wordt gemarkeerd (deleted_at) en globaal uit reads gefilterd,
    met audit-snapshot zodat het financiële feit in de history bewaard blijft."""
    record = db.query(PaymentRecord).filter(PaymentRecord.id == record_id).first()
    if not record:
        raise HTTPException(status_code=404, detail="Payment record not found")
    # Een betaling waar effectief geld bewoog, mag niet verdwijnen (#218):
    #   1) een online betaling die Mollie als 'paid' bevestigde;
    #   2) elk record met een betaald/ontvangen bedrag (cash/overschrijving bevestigd,
    #      of een uitgevoerde terugbetaling — amount_paid ≠ 0).
    # Zo'n record corrigeer je via een terugbetaling, niet via verwijderen.
    if record.method == "online" and record.status == "paid":
        raise HTTPException(
            status_code=400,
            detail="Een door Mollie betaalde online betaling kan niet verwijderd worden.",
        )
    if record.amount_paid is not None and record.amount_paid != 0:
        raise HTTPException(
            status_code=400,
            detail="Een betaling met een ontvangen/betaald bedrag kan niet verwijderd worden.",
        )
    snapshot_payment_record(
        db, record,
        operation="delete", action="payment_deleted",
        source="admin_manual", actor=admin.email,
    )
    soft_delete(record)
    db.commit()
