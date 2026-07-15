from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Optional, Tuple
from sqlalchemy import distinct, func
from sqlalchemy.orm import Session
from .models import PaymentRecord
from app.domains.membership.api import Membership
from app.domains.mdm.api import MemberPerson, Person
from app.domains.audit.api import snapshot_payment_record

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

    'Geldig vandaag' = ``is_active`` én ``valid_from <= today <= valid_to`` (beide
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
        from app.domains.payment.gateway_service import create_payment as gw_create
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
        # Overschrijving: genereer een unieke gestructureerde mededeling (OGM) zodat
        # de inschrijver met referentie betaalt en de penningmeester kan reconciliëren (#157).
        if method == "transfer":
            from sqlalchemy import text
            from app.domains.payment.structured_communication import generate_structured_communication
            seq = db.execute(text("SELECT nextval('payment_ogm_seq')")).scalar()
            record.structured_communication = generate_structured_communication(int(seq))

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
    """Called by gateway webhook handler to propagate status to PaymentRecord.

    Idempotent en concurrency-veilig (#91): we vergrendelen de betrokken
    PaymentRecord-rij(en) (SELECT ... FOR UPDATE) zodat gelijktijdige/herhaalde
    webhooks serialiseren. Een herhaalde 'paid' is een no-op (status ongewijzigd →
    `continue`) en stempelt paid_at/amount_paid niet opnieuw. Een DB-unieke index
    op gateway_payment_id garandeert bovendien max. één record per gateway-betaling."""
    records = db.query(PaymentRecord).filter(
        PaymentRecord.gateway_payment_id == gateway_payment_id
    ).with_for_update().all()
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
        # Kernel-event (§5.8, trede 1): consumenten reageren op de bevestiging
        # zonder dit component te importeren. Binnen dezelfde transactie; de
        # idempotente no-op hierboven voorkomt dubbele publicatie.
        if new_status == "paid":
            from app.kernel.contracts.payment import PaymentSettled
            from app.kernel.events import publish

            publish(PaymentSettled(
                payment_record_id=record.id, payable_type=record.payable_type,
                payable_id=record.payable_id, amount=str(record.amount),
                method=record.method,
            ), db)


def _activate_membership(db: Session, membership_id: int, source: str, actor: Optional[str]) -> None:
    """Zet een lidmaatschap actief na bevestigde betaling. Idempotent: een reeds
    actief lidmaatschap wordt niet opnieuw aangeraakt (geen dubbele history-rij)."""
    from app.domains.membership.api import Membership
    from app.domains.audit.api import snapshot_membership

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
    # Defense-in-depth (#146): betaald bedrag mag het verschuldigde nooit overschrijden.
    # Tekengevoelig (#219): charge → [0, amount]; refund (negatief) → [amount, 0].
    if amount_paid is not None:
        lo, hi = sorted((Decimal("0"), Decimal(str(record.amount))))
        if not (lo <= amount_paid <= hi):
            raise ValueError(
                f"Betaald bedrag ({amount_paid}) moet tussen {lo} en {hi} liggen."
            )
    record.status = "paid"
    record.paid_at = datetime.now(timezone.utc)
    if note:
        record.note = note
    # amount_paid vóór de snapshot zetten, zodat de history het juiste bedrag vastlegt.
    # #199: zonder expliciet bedrag → het volledige verschuldigde (resp. de volledige
    # refund) boeken, zodat het saldo meteen klopt en één klik "betaald" volstaat.
    record.amount_paid = amount_paid if amount_paid is not None else record.amount
    db.flush()
    snapshot_payment_record(
        db, record,
        operation="update", action="payment_manually_confirmed",
        source="admin_manual", actor=actor,
    )
    # Handmatige bevestiging van een lidmaatschap-betaling (cash/overschrijving of
    # een vastgelopen online betaling) moet het lidmaatschap ook activeren — net
    # als de Mollie-webhook doet. Idempotent. #143
    if record.payable_type == "membership":
        _activate_membership(db, record.payable_id, source="admin_manual", actor=actor)
    return record


def get_records_for(db: Session, payable_type: str, payable_id: int) -> list[PaymentRecord]:
    return db.query(PaymentRecord).filter(
        PaymentRecord.payable_type == payable_type,
        PaymentRecord.payable_id == payable_id,
    ).all()


def net_paid(db: Session, payable_type: str, payable_id: int) -> Decimal:
    """Netto ontvangen bedrag op een payable: som van amount_paid over alle
    records (charges positief, refunds negatief). Een nog niet betaalde charge
    (amount_paid is None) telt als 0."""
    rows = db.query(PaymentRecord.amount_paid).filter(
        PaymentRecord.payable_type == payable_type,
        PaymentRecord.payable_id == payable_id,
    ).all()
    return sum((Decimal(str(r[0])) for r in rows if r[0] is not None), Decimal("0"))


def create_refund(
    db: Session,
    charge_record_id: str,
    amount: Decimal,
    *,
    note: Optional[str] = None,
    method: str = "transfer",
    actor: Optional[str] = None,
    source: str = "admin_manual",
    settled: bool = True,
) -> PaymentRecord:
    """Registreer een terugbetaling als apart PaymentRecord (#83).

    Een refund is een negatief record met ``type="refund"`` dat via
    ``refund_of_id`` naar de oorspronkelijke charge wijst. ``amount`` is het
    **positieve** terug te betalen bedrag. Invarianten (service-laag, zodat elke
    aanroeper beschermd is):
      - je kunt enkel een 'charge' terugbetalen, geen refund;
      - het bedrag is strikt positief;
      - je kunt nooit méér terugbetalen dan er netto ontvangen is op de payable.

    ``settled``: True wanneer de penningmeester een reeds uitgevoerde
    terugbetaling registreert (meteen ``paid``, geld is terug). False voor een
    automatisch gegenereerde **verplichting** (bv. bij bestelverlaging, #216): de
    refund staat dan ``pending`` met ``amount_paid=None`` tot de penningmeester de
    effectieve terugstorting bevestigt. Zo wordt het geld nooit als teruggestort
    getoond vóór iemand het echt heeft uitbetaald.
    """
    charge = db.query(PaymentRecord).filter(PaymentRecord.id == charge_record_id).first()
    if not charge:
        raise ValueError(f"PaymentRecord {charge_record_id} not found")
    if charge.type != "charge":
        raise ValueError("Een terugbetaling kan enkel een 'charge'-record terugdraaien.")

    refund_amount = Decimal(str(amount))
    if refund_amount <= 0:
        raise ValueError("Het terug te betalen bedrag moet strikt positief zijn.")

    available = net_paid(db, charge.payable_type, charge.payable_id)
    if refund_amount > available:
        raise ValueError(
            f"Kan niet meer terugbetalen ({refund_amount}) dan er netto ontvangen is ({available})."
        )

    record = PaymentRecord(
        payable_type=charge.payable_type,
        payable_id=charge.payable_id,
        amount=-refund_amount,
        amount_paid=(-refund_amount if settled else None),
        method=method,
        status=("paid" if settled else "pending"),
        type="refund",
        refund_of_id=charge.id,
        note=note,
        paid_at=(datetime.now(timezone.utc) if settled else None),
    )
    db.add(record)
    db.flush()
    snapshot_payment_record(
        db, record,
        operation="insert", action="payment_refunded",
        source=source, actor=actor,
    )
    return record


_EDITABLE_STATUSES = {"pending", "paid", "failed", "cancelled"}


def refresh_record_status(db: Session, record_id: str, actor: Optional[str] = None) -> PaymentRecord:
    """Ververs de status van een online betaling bij de provider (Mollie) en pas
    ze toe op de PaymentRecord(s) — de handmatige tegenhanger van de webhook
    (#455). Enkel zinvol voor een record met een gekoppelde gateway-betaling."""
    from app.domains.payment.gateway_service import refresh_payment_status

    record = db.query(PaymentRecord).filter(PaymentRecord.id == record_id).first()
    if not record:
        raise ValueError(f"PaymentRecord {record_id} not found")
    if not record.gateway_payment_id:
        raise ValueError("Deze betaling heeft geen online (Mollie) betaling om te verversen.")
    gp = refresh_payment_status(db, record.gateway_payment_id)
    # 'needs_review' (bedrag-mismatch, #92) niet automatisch als betaald boeken.
    if gp.status in _GATEWAY_ACTION:
        handle_gateway_update(db, gp.id, gp.status, source="admin_refresh", actor=actor)
    db.refresh(record)
    return record


def set_payment_status(db: Session, record_id: str, status: str,
                       actor: Optional[str] = None, note: Optional[str] = None) -> PaymentRecord:
    """Vrije status-correctie door de penningmeester (#455). Enkel binnen de
    gekende set; bij 'paid' wordt (als nog niet betaald) paid_at/amount_paid gezet,
    bij elke andere status worden die gewist zodat het bedrag niet meer meetelt in
    het saldo. Alles met een history-snapshot voor de audittrail."""
    if status not in _EDITABLE_STATUSES:
        raise ValueError(f"Ongeldige status '{status}'.")
    record = db.query(PaymentRecord).filter(PaymentRecord.id == record_id).first()
    if not record:
        raise ValueError(f"PaymentRecord {record_id} not found")
    record.status = status
    if status == "paid":
        if record.paid_at is None:
            record.paid_at = datetime.now(timezone.utc)
        if record.amount_paid is None:
            record.amount_paid = record.amount
    else:
        record.paid_at = None
        record.amount_paid = None
    if note:
        record.note = note
    db.flush()
    snapshot_payment_record(
        db, record, operation="update", action="payment_status_edited",
        source="admin_manual", actor=actor,
    )
    if status == "paid" and record.payable_type == "membership":
        _activate_membership(db, record.payable_id, source="admin_manual", actor=actor)
    return record


def void_payment_record(db: Session, record_id: str,
                        actor: Optional[str] = None, note: Optional[str] = None) -> PaymentRecord:
    """Verwijder (soft-delete) een betaal-/terugbetaalrecord (#455). De globale
    soft-delete-filter sluit het daarna uit van elke saldoberekening, dus het
    bedrag telt niet meer mee — omkeerbaar en met een history-snapshot. Zo
    corrigeer je ook een foute refund: verwijder ze en registreer eventueel een
    nieuwe."""
    from app.soft_delete import soft_delete

    record = db.query(PaymentRecord).filter(PaymentRecord.id == record_id).first()
    if not record:
        raise ValueError(f"PaymentRecord {record_id} not found")
    if note:
        record.note = note
    # Snapshot vóór de soft-delete (de bronrij blijft bestaan maar wordt gefilterd).
    snapshot_payment_record(
        db, record, operation="delete", action="payment_voided",
        source="admin_manual", actor=actor,
    )
    soft_delete(record)
    db.flush()
    return record


def registration_balance(db: Session, registration) -> dict:
    """Financiële stand van één inschrijving (#83): verschuldigd vs. netto betaald.

    ``balance > 0`` → nog te ontvangen, ``< 0`` → te veel ontvangen (refund due),
    ``= 0`` → vereffend. De live DB is de enige bron van waarheid.
    """
    from app.domains.activities.api import compute_registration_total

    total_due, _ = compute_registration_total(registration)
    records = get_records_for(db, "registration", registration.id)
    total_paid = sum(
        (Decimal(str(r.amount_paid)) for r in records if r.amount_paid is not None),
        Decimal("0"),
    )
    total_refunded = -sum(
        (Decimal(str(r.amount_paid)) for r in records
         if r.type == "refund" and r.amount_paid is not None),
        Decimal("0"),
    )
    return {
        "total_due": total_due,
        "total_paid": total_paid,
        "total_refunded": total_refunded,
        "balance": total_due - total_paid,
    }


def reconcile_registration_charges(
    db: Session, registration, *, audit_actor: Optional[str] = None
) -> None:
    """Herreken integraal bij elke bestelwijziging (#195): de reeds **betaalde**
    bedragen zijn de waarheid; het openstaande saldo wordt herleid tot één open post.

    - Onbetaalde (pending) charges/refunds worden verwijderd (ze worden herrekend).
    - Een partieel betaalde charge wordt gesloten op zijn effectief betaalde bedrag.
    - ``saldo = besteltotaal − netto ontvangen``:
        * > 0 → één openstaande ``transfer``-charge (met OGM);
        * < 0 → één terugbetaling van het te veel ontvangene.

    Invariant na afloop: som van alle (niet-verwijderde) records == besteltotaal.
    """
    from app.domains.activities.api import compute_registration_total
    from app.soft_delete import soft_delete

    total_due = Decimal(str(compute_registration_total(registration)[0]))
    records = get_records_for(db, "registration", registration.id)

    net_paid = sum(
        (Decimal(str(r.amount_paid)) for r in records if r.amount_paid is not None),
        Decimal("0"),
    )
    paid_charge = None
    for r in records:
        if r.amount_paid is None:
            # Open (onbetaalde) post → weg; het openstaande wordt herleid tot één post.
            snapshot_payment_record(
                db, r, operation="delete", action="order_reconciled",
                source="order-edit", actor=audit_actor,
            )
            soft_delete(r)
        else:
            # Betaalde post = waarheid; sluit een partieel betaalde charge op zijn
            # effectief betaalde bedrag.
            if Decimal(str(r.amount)) != Decimal(str(r.amount_paid)):
                r.amount = r.amount_paid
                snapshot_payment_record(
                    db, r, operation="update", action="order_reconciled",
                    source="order-edit", actor=audit_actor,
                )
            if r.type == "charge" and Decimal(str(r.amount_paid)) > 0:
                paid_charge = r

    outstanding = total_due - net_paid
    if outstanding > 0:
        # Eén openstaande charge voor het volledige openstaande bedrag (met OGM).
        create_payment_record(
            db, "registration", registration.id, amount=outstanding, method="transfer",
            audit_source="order-edit", audit_actor=audit_actor,
        )
    elif outstanding < 0 and paid_charge is not None:
        # Te veel ontvangen → één terugbetaling, met de methode van de betaalde charge.
        method = paid_charge.method if paid_charge.method in ("transfer", "cash") else "transfer"
        # Verplichting, geen voldongen feit: de penningmeester bevestigt de
        # effectieve terugstorting (#216). Daarom pending, niet meteen 'paid'.
        create_refund(
            db, paid_charge.id, -outstanding, method=method,
            note="Automatisch bij bestelverlaging — terugstorting te bevestigen",
            actor=audit_actor, source="order-edit", settled=False,
        )
    db.flush()
