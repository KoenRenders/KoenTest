from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional, Tuple
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session
from .models import PaymentRecord
from app.domains.membership.api import Membership
from app.domains.mdm.api import MemberPerson, Person
from app.domains.audit.api import snapshot_payment_record

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

    De datumgrenzen en bedragen komen per tenant uit de tenant-config
    (branding-slice #407), met de .env-settings als default.
    """
    from app.kernel.tenant_config import tenant_membership_config

    conf = tenant_membership_config()
    if today is None:
        today = date.today()
    half_start = _parse_md(conf["half_start_md"], today.year)
    half_end = _parse_md(conf["half_end_md"], today.year)
    if half_start <= today <= half_end:
        return conf["price_half"]
    return conf["price_full"]


def membership_valid_period(paid_at: Optional[date] = None) -> Tuple[date, date]:
    """Geeft (valid_from, valid_to) voor een nieuw lidmaatschap.

    Regel: betaling vanaf MEMBERSHIP_NEXT_YEAR_FROM_MD dekt ook het volgende
    kalenderjaar (valid_to = 31 dec volgend jaar), betaling daarvoor enkel
    het huidige jaar (valid_to = 31 dec dit jaar).
    """
    from app.kernel.tenant_config import tenant_membership_config

    if paid_at is None:
        paid_at = date.today()
    next_year_cutoff = _parse_md(tenant_membership_config()["next_year_from_md"], paid_at.year)
    valid_from = paid_at
    if paid_at >= next_year_cutoff:
        valid_to = date(paid_at.year + 1, 12, 31)
    else:
        valid_to = date(paid_at.year, 12, 31)
    return valid_from, valid_to


def current_membership_counts(db: Session, today: Optional[date] = None) -> Tuple[int, int]:
    """Aantal vandaag-geldige lidmaatschappen en de eraan gekoppelde personen (#294).

    'Geldig vandaag' = ``is_active`` Ã©n ``valid_from <= today <= valid_to`` (beide
    gezet). Een lidmaatschap dat vandaag verlopen of nog niet ingegaan is, telt niet
    mee. Soft-deleted leden/personen/lidmaatschappen vallen automatisch weg via de
    globale ORM-filter. Retourneert ``(gezinnen, personen)``.
    """
    if today is None:
        today = date.today()
    valid = (
        Membership.is_active.is_(True),
        Membership.valid_from.isnot(None),
        Membership.valid_to.isnot(None),
        Membership.valid_from <= today,
        Membership.valid_to >= today,
    )
    households = (
        db.query(func.count(distinct(Membership.member_id))).filter(*valid).scalar()
    ) or 0
    persons = (
        db.query(func.count(distinct(MemberPerson.person_id)))
        .join(Membership, Membership.member_id == MemberPerson.member_id)
        # Join Person zodat de globale soft-delete-filter verwijderde personen
        # uitsluit (een MemberPerson-rij blijft anders verwijzen naar een dood lid).
        .join(Person, Person.id == MemberPerson.person_id)
        .filter(*valid)
        .scalar()
    ) or 0
    return households, persons


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
        # Handle online payment logic here if needed
        pass
    
    record = PaymentRecord(
        payable_type=payable_type,
        payable_id=payable_id,
        amount_paid=amount,
        method=method,
        redirect_url=redirect_url,
        description=description,
        audit_source=audit_source,
        audit_actor=audit_actor,
    )
    
    if method == "online":
        # Set appropriate status for online payments
        record.status = _GATEWAY_ACTION.get("online", "pending")
    else:
        # For direct transfers and refunds, the status depends on the amount
        record.status = _GATEWAY_ACTION.get("paid", "pending")
    
    db.add(record)
    db.commit()
    return record