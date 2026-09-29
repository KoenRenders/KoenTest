from typing import List

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import User, get_current_finance, get_finance_or_admin
from app.i18n import _

from .models import PaymentError, PaymentRecord
from .schemas import (
    PaymentRecordResponse,
    PaymentRecordUpdate,
    RefundCreate,
    RegistrationBalance,
)
from .service import (
    create_refund,
    edit_payment_record,
    get_records_for,
    refresh_record_status,
    registration_balance,
)
from .service import delete_payment_record as delete_record

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
    from app.domains.payment.exports import build_payments_export_ods

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
        raise HTTPException(status_code=404, detail=_("Payment record not found"))
    # The rule and the refresh are the service's (CR-13 phase 2): only an online
    # payment with a gateway payment is refreshed, and only to a status we know.
    try:
        refresh_record_status(db, record_id, actor=admin.email)
    except PaymentError as refusal:
        raise HTTPException(status_code=400, detail=str(refusal))
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
            db,
            record_id,
            data.amount,
            note=data.note,
            method=data.method,
            actor=admin.email,
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
    from app.domains.activities.api import Registration

    reg = db.query(Registration).filter(Registration.id == registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail=_("Registration not found"))
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
        raise HTTPException(status_code=404, detail=_("Payment record not found"))

    # Eén gedeelde service-regel voor status + bedrag + opmerking (#515), zodat de
    # JSON-API en de admin-UI ("Bewerken") niet uiteenlopen. De tekengevoelige
    # bedrag-grens (#219) en de #517 refund-invariant zitten in de service.
    try:
        edit_payment_record(
            db,
            record_id,
            status=data.status,
            amount_paid=data.amount_paid,
            note=data.note,
            actor=admin.email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

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
    # The rule is the service's (CR-13 phase 2): it stood here a second time.
    try:
        record = delete_record(db, record_id, actor=admin.email)
    except PaymentError as refusal:
        raise HTTPException(status_code=400, detail=str(refusal))
    if record is None:
        raise HTTPException(status_code=404, detail=_("Payment record not found"))
    db.commit()
