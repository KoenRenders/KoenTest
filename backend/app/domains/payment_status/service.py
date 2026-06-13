from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional, Tuple
from sqlalchemy.orm import Session
from .models import PaymentRecord
from app.domains.audit.service import snapshot_payment_record

# Semantische history-actie per (interne) gateway-status, zodat de tijdlijn
# meteen toont wat de gateway/admin-refresh meldde i.p.v. een generiek label.
_GATEWAY_ACTION = {
    "paid": "payment_paid",
    "failed": "payment_failed",
    "cancelled": "payment_cancelled",
    "pending": "payment_pending",
}


def _parse_md(md_str: str, year: int) -> date:
    """Zet "MM-DD" om naar een datum in het opgegeven jaar."""
    month, day = md_str.split("-")
    return date(year, int(month), int(day))


def membership_price_for_date(today: Optional[date] = None) -> Decimal:
    """Geeft de lidmaatschapsprijs op basis van de datum (vol of half).

    De datumgrenzen en bedragen komen uit de app-configuratie:
      MEMBERSHIP_HALF_PRICE_START_MD / END_MD en MEMBERSHIP_PRICE_FULL / HALF.
    """
    from app.config import settings
    if today is None:
        today = date.today()
    half_start = _parse_md(settings.membership_half_price_start_md, today.year)
    half_end = _parse_md(settings.membership_half_price_end_md, today.year)
    if half_start <= today <= half_end:
        return settings.membership_price_half
    return settings.membership_price_full


def membership_valid_period(paid_at: Optional[date] = None) -> Tuple[date, date]:
    """Geeft (valid_from, valid_to) voor een nieuw lidmaatschap.

    Regel: betaling vanaf MEMBERSHIP_NEXT_YEAR_FROM_MD dekt ook het volgende
    kalenderjaar (valid_to = 31 dec volgend jaar), betaling daarvoor enkel
    het huidige jaar (valid_to = 31 dec dit jaar).
    """
    from app.config import settings
    if paid_at is None:
        paid_at = date.today()
    next_year_cutoff = _parse_md(settings.membership_next_year_from_md, paid_at.year)
    valid_from = paid_at
    if paid_at >= next_year_cutoff:
        valid_to = date(paid_at.year + 1, 12, 31)
    else:
        valid_to = date(paid_at.year, 12, 31)
    return valid_from, valid_to


def create_payment_record(
    db: Session,
    payable_type: str,
    payable_id: int,
    amount: Decimal,
    method: str,
    redirect_url: Optional[str] = None,
    description: Optional[str] = None,
    audit_source: str = "system",
    audit_actor: Optional[str] = None,
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
    snapshot_payment_record(
        db, record,
        operation="insert", action="payment_created",
        source=audit_source, actor=audit_actor,
    )
    return record


def handle_gateway_update(
    db: Session,
    gateway_payment_id: str,
    new_status: str,
    source: str = "mollie",
    actor: Optional[str] = None,
) -> None:
    """Called by gateway webhook handler to propagate status to PaymentRecord."""
    records = db.query(PaymentRecord).filter(
        PaymentRecord.gateway_payment_id == gateway_payment_id
    ).all()
    for record in records:
        if record.status == new_status:
            continue
        record.status = new_status
        if new_status == "paid" and record.paid_at is None:
            record.paid_at = datetime.now(timezone.utc)
            record.amount_paid = record.amount
        snapshot_payment_record(
            db, record,
            operation="update", action=_GATEWAY_ACTION.get(new_status, "payment_status_changed"),
            source=source, actor=actor,
        )
        # Lidmaatschap-betaling bevestigd -> lidmaatschap activeren (#113). Geldt
        # zowel voor een nieuwe gezinsregistratie als voor een vernieuwing vanuit
        # het gezinscherm: beide maken een Membership (is_active=False) met
        # payable_type="membership", payable_id=membership.id.
        if new_status == "paid" and record.payable_type == "membership":
            _activate_membership(db, record.payable_id, source=source, actor=actor)


def _activate_membership(db: Session, membership_id: int, source: str, actor: Optional[str]) -> None:
    """Zet een lidmaatschap actief na bevestigde betaling. Idempotent: een reeds
    actief lidmaatschap wordt niet opnieuw aangeraakt (geen dubbele history-rij)."""
    from app.models.member import Membership
    from app.domains.audit.service import snapshot_membership

    ms = db.query(Membership).filter(Membership.id == membership_id).first()
    if ms is None or ms.is_active:
        return
    ms.is_active = True
    if ms.valid_from is None or ms.valid_to is None:
        vf, vt = membership_valid_period(date.today())
        ms.valid_from = ms.valid_from or vf
        ms.valid_to = ms.valid_to or vt
    db.flush()
    snapshot_membership(db, ms, operation="update", action="membership_activated",
                        source=source, actor=actor)


def confirm_manual_payment(
    db: Session,
    record_id: str,
    note: Optional[str] = None,
    actor: Optional[str] = None,
    amount_paid: Optional[Decimal] = None,
) -> PaymentRecord:
    record = db.query(PaymentRecord).filter(PaymentRecord.id == record_id).first()
    if not record:
        raise ValueError(f"PaymentRecord {record_id} not found")
    record.status = "paid"
    record.paid_at = datetime.now(timezone.utc)
    if note:
        record.note = note
    # amount_paid vóór de snapshot zetten, zodat de history het juiste bedrag vastlegt.
    if amount_paid is not None:
        record.amount_paid = amount_paid
    db.flush()
    snapshot_payment_record(
        db, record,
        operation="update", action="payment_manually_confirmed",
        source="admin_manual", actor=actor,
    )
    return record


def get_records_for(db: Session, payable_type: str, payable_id: int) -> list[PaymentRecord]:
    return db.query(PaymentRecord).filter(
        PaymentRecord.payable_type == payable_type,
        PaymentRecord.payable_id == payable_id,
    ).all()
