from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
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
    # Refund-bewuste invariant (#517): een charge die al (deels) terugbetaald is,
    # mag zijn ontvangen bedrag NIET stil verlaagd krijgen — dat maakt de netto-
    # positie incoherent met de reeds uitbetaalde terugbetaling (bv. €30 ontvangen,
    # €10 terug, dan "€20 betaald" → net €10 i.p.v. €20). `create_refund` bewaakt de
    # andere kant al; dit is de omgekeerde weg. Blokkeren i.p.v. stil overschrijven;
    # de penningmeester corrigeert dan via de terugbetaling.
    if amount_paid is not None and record.type == "charge":
        refund_rows = db.query(PaymentRecord.amount_paid).filter(
            PaymentRecord.payable_type == record.payable_type,
            PaymentRecord.payable_id == record.payable_id,
            PaymentRecord.type == "refund",
        ).all()
        total_refunded = -sum(
            (Decimal(str(r[0])) for r in refund_rows if r[0] is not None), Decimal("0"))
        if total_refunded > 0:
            current = (Decimal(str(record.amount_paid))
                       if record.amount_paid is not None else Decimal("0"))
            # Enkel een VERLAGING van het reeds-ontvangen bedrag van deze charge is
            # incoherent na een refund; een nieuwe/hogere betaling (bv. een partieel
            # betaalde open charge na een eerdere bestelverlaging) blijft toegestaan.
            if amount_paid < current:
                raise ValueError(
                    "Deze betaling is al (deels) terugbetaald — je kunt het ontvangen "
                    "bedrag niet verlagen zonder de terugbetaling te verrekenen. "
                    "Corrigeer eerst de terugbetaling."
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


def edit_payment_record(
    db: Session,
    record_id: str,
    *,
    status: Optional[str] = None,
    amount_paid: Optional[Decimal] = None,
    note: Optional[str] = None,
    actor: Optional[str] = None,
) -> PaymentRecord:
    """Geünificeerde 'Bewerken' van één betaal-/terugbetaalrecord (#515): status +
    betaald bedrag + opmerking in één bewerking, voor **charges én refunds**. Eén
    plek voor de regels — gebruikt door de admin-UI én de JSON-API, zodat de
    validatie niet uiteenloopt.

    - ``amount_paid`` wordt tekengevoelig gevalideerd binnen ``[0, amount]`` (charge)
      resp. ``[amount, 0]`` (refund, negatief) — zo registreer je op een refund de
      effectief uitbetaalde som.
    - ``status == "paid"`` loopt via :func:`confirm_manual_payment` (incl.
      lidmaatschap-activatie en de #517 refund-bewuste invariant); een leeg bedrag
      boekt dan de volledige (terug)betaling.
    - een andere status schrijft status/bedrag/opmerking direct weg met snapshot.
    """
    record = db.query(PaymentRecord).filter(PaymentRecord.id == record_id).first()
    if not record:
        raise ValueError(f"PaymentRecord {record_id} not found")
    # Tekengevoelige grens (#219), zelfde regel als de JSON-API: charge → [0, amount];
    # refund (negatief) → [amount, 0]. Hier al zodat een niet-'paid'-bewerking het ook
    # afdwingt (confirm_manual_payment valideert het zelf nogmaals voor de 'paid'-tak).
    if amount_paid is not None:
        lo, hi = sorted((Decimal("0"), Decimal(str(record.amount))))
        if not (lo <= amount_paid <= hi):
            raise ValueError(
                f"Betaald bedrag ({amount_paid}) moet tussen {lo} en {hi} liggen."
            )
    if status == "paid":
        return confirm_manual_payment(db, record_id, note, actor=actor, amount_paid=amount_paid)
    if status is not None:
        if status not in _EDITABLE_STATUSES:
            raise ValueError(f"Ongeldige status '{status}'.")
        record.status = status
    if note is not None:
        record.note = note
    if amount_paid is not None:
        record.amount_paid = amount_paid
        # Consistentie (#346): een ontvangen/terugbetaald bedrag (≠ 0) krijgt meteen
        # een paid_at, zodat er nooit een "betaald zonder datum"-record ontstaat.
        if amount_paid != 0 and record.paid_at is None:
            record.paid_at = datetime.now(timezone.utc)
    db.flush()
    snapshot_payment_record(
        db, record, operation="update", action="payment_updated",
        source="admin_update", actor=actor,
    )
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


def reconcile_charges(
    db: Session, payable_type: str, payable_id: int, total_due, *,
    audit_actor: Optional[str] = None, source: str = "order-edit",
    refund_note: str = "Automatisch bij bestelverlaging — terugstorting te bevestigen",
) -> None:
    """Herreken integraal naar ``total_due`` (#195, veralgemeend in #619).

    De reeds **betaalde** bedragen zijn de waarheid; het openstaande saldo wordt
    herleid tot één open post.

    - Onbetaalde (pending) charges/refunds worden verwijderd (ze worden herrekend).
    - Een partieel betaalde charge wordt gesloten op zijn effectief betaalde bedrag.
    - ``saldo = total_due − netto ontvangen``:
        * > 0 → één openstaande ``transfer``-charge (met OGM);
        * < 0 → één terugbetaling van het te veel ontvangene.

    Invariant na afloop: som van alle (niet-verwijderde) records == ``total_due``.

    Eén definitie voor beide payables (#619). Bij activiteiten volgde de financiële
    kant een bestelwijziging al; bij lidmaatschappen gebeurde er niets, waardoor een
    geschrapt lidmaatschap ofwel een eeuwige vordering achterliet ofwel een betaling
    zonder terugbetaling. Een tweede, eigen implementatie zou vroeg of laat afwijken —
    en dit is geld.
    """
    from app.soft_delete import soft_delete

    total_due = Decimal(str(total_due))
    records = get_records_for(db, payable_type, payable_id)

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
                source=source, actor=audit_actor,
            )
            soft_delete(r)
        else:
            # Betaalde post = waarheid; sluit een partieel betaalde charge op zijn
            # effectief betaalde bedrag.
            if Decimal(str(r.amount)) != Decimal(str(r.amount_paid)):
                r.amount = r.amount_paid
                snapshot_payment_record(
                    db, r, operation="update", action="order_reconciled",
                    source=source, actor=audit_actor,
                )
            if r.type == "charge" and Decimal(str(r.amount_paid)) > 0:
                paid_charge = r

    outstanding = total_due - net_paid
    if outstanding > 0:
        # Eén openstaande charge voor het volledige openstaande bedrag (met OGM).
        create_payment_record(
            db, payable_type, payable_id, amount=outstanding, method="transfer",
            audit_source=source, audit_actor=audit_actor,
        )
    elif outstanding < 0 and paid_charge is not None:
        # Te veel ontvangen → één terugbetaling, met de methode van de betaalde charge.
        method = paid_charge.method if paid_charge.method in ("transfer", "cash") else "transfer"
        # Verplichting, geen voldongen feit: de penningmeester bevestigt de
        # effectieve terugstorting (#216). Daarom pending, niet meteen 'paid'.
        create_refund(
            db, paid_charge.id, -outstanding, method=method,
            note=refund_note, actor=audit_actor, source=source, settled=False,
        )
    db.flush()


def reconcile_registration_charges(
    db: Session, registration, *, audit_actor: Optional[str] = None
) -> None:
    """Herreken de charges van een inschrijving naar haar besteltotaal (#185/#195).

    Dunne laag over :func:`reconcile_charges`; het besteltotaal komt uit
    ``compute_registration_total``, de enige bron voor "wat kost deze inschrijving".
    """
    from app.domains.activities.api import compute_registration_total

    reconcile_charges(db, "registration", registration.id,
                      compute_registration_total(registration)[0],
                      audit_actor=audit_actor)


# ── Wat het betalingenscherm en de export samen nodig hebben (#635 punt 4/9) ──
# Filter, aggregatie, kaartgroepering en afgeleide status stonden in de UI-route
# (payment/ui.py) en, half, nog eens in exports.py. Ze waren al uit elkaar gelopen:
# het scherm kende `failed`/`cancelled` en vrije zoektekst, de export niet; de
# export eiste payable_type == "registration" bij een onderdeelfilter, het scherm
# niet. Wie op het scherm filterde en dan exporteerde, kreeg iets anders. Eén
# implementatie, twee ingangen.

_SALDO_DREMPEL = Decimal("0.001")   # afrondingsruis is geen openstaand saldo


def _bedrag(waarde) -> Decimal:
    return Decimal(str(waarde or 0))


def matches_filter(record, *, context: str = "all", status: str = "all", q: str = "",
                   membership_year=None, component_id=None) -> bool:
    """Hoort dit record bij het gekozen filter?

    `membership_year`/`component_id` mogen expliciet meegegeven worden voor
    aanroepers die ze zelf afleiden (de export verrijkt de rauwe records); anders
    komen ze van het record zelf, zoals het scherm ze krijgt.

    Volgorde is betekenisvol: de zoekterm staat vóór de andere filters, zodat je
    binnen het gekozen filter zoekt en niet erbuiten (#591).
    """
    jaar = membership_year if membership_year is not None else getattr(record, "membership_year", None)
    comp = component_id if component_id is not None else getattr(record, "component_id", None)

    term = (q or "").strip().lower()
    if term:
        velden = (getattr(record, "contact_name", None),
                  getattr(record, "structured_communication", None),
                  getattr(record, "description", None),
                  getattr(record, "component_name", None))
        if not any(term in (waarde or "").lower() for waarde in velden):
            return False

    if context == "membership" and record.payable_type != "membership":
        return False
    if context.startswith("year-"):
        if record.payable_type != "membership" or jaar != int(context[5:]):
            return False
    if context.startswith("comp-"):
        # payable_type meecontroleren (kwam uit de export-variant): een
        # component_id hoort per definitie bij een inschrijving.
        if record.payable_type != "registration" or comp != int(context[5:]):
            return False

    if status == "openstaand":
        # Openstaand komt uit het saldo, niet uit de statuskolom: betaald =
        # waarheid (#198).
        return (_bedrag(record.amount) - _bedrag(record.amount_paid)) > _SALDO_DREMPEL
    if status in ("pending", "paid", "failed", "cancelled"):
        return record.status == status
    return True


def filter_records(records, *, context: str = "all", status: str = "all", q: str = "") -> list:
    return [r for r in records if matches_filter(r, context=context, status=status, q=q)]


def aggregate(records) -> dict:
    """Te betalen / ontvangen / saldo over een verzameling records."""
    due = sum((_bedrag(r.amount) for r in records), Decimal("0"))
    paid = sum((_bedrag(r.amount_paid) for r in records), Decimal("0"))
    return {"due": due, "paid": paid, "saldo": due - paid}


def derived_status(record) -> str:
    """De status zoals ze op het scherm hoort te staan.

    De kolom `status` kent "Deels betaald" niet: dat is een *afgeleide* toestand
    (pending met een gedeeltelijke betaling) die de template zelf uitrekende — een
    regel die zo alleen in Jinja bestond en nergens testbaar was (#635 punt 9).
    Ook een terugbetaling die nog uitbetaald moet worden krijgt hier haar eigen
    naam, zodat het scherm niet op `type` én `status` hoeft te puzzelen.

    Waarden: paid · refund_due · partial · pending · failed · cancelled · <rauw>.
    """
    if record.status == "paid":
        return "paid"
    if getattr(record, "type", None) == "refund" and record.status == "pending":
        return "refund_due"
    if record.status == "pending":
        betaald = record.amount_paid
        if betaald is not None and _bedrag(betaald) != 0:
            return "partial"
        return "pending"
    return record.status


def may_delete(record) -> bool:
    """Mag dit record verwijderd worden? Dezelfde regel als de guard in
    status_router (#218/#617-2c), zodat het scherm geen knop toont die de guard
    daarna weigert."""
    if record.method == "online" and record.status == "paid":
        return False
    return record.amount_paid is None or _bedrag(record.amount_paid) == 0


def group_cards(records) -> list[dict]:
    """Groepeer records tot wat één kaartenlijst per payable toont.

    Per groep (payable_type, payable_id): de charges met hun eigen refunds
    (`refund_of_id`), de onderliggende records en het totaal. Wees-refunds — hun
    charge valt buiten het filter — krijgen een eigen kaart, anders verdwijnen ze
    stil van het scherm.

    `toon_totaal` staat aan zodra een payable meer dan één record heeft: de
    totaalregel telt de héle inschrijving, niet één charge met haar refunds. Dat
    laatste was de fout van #617-2e — een inschrijving met twee charges kreeg twee
    regels die geen van beide de inschrijving telden.
    """
    charges = [r for r in records if r.type != "refund"]
    refunds = [r for r in records if r.type == "refund"]

    per_charge: dict = {}
    for r in refunds:
        if r.refund_of_id:
            per_charge.setdefault(r.refund_of_id, []).append(r)
    charge_ids = {r.id for r in charges}

    kaarten = [(r, per_charge.get(r.id, [])) for r in charges]
    kaarten += [(r, []) for r in refunds
                if not r.refund_of_id or r.refund_of_id not in charge_ids]
    kaarten.sort(key=lambda p: p[0].created_at, reverse=True)

    groepen: list[dict] = []
    volgorde: dict = {}
    for charge, eigen_refunds in kaarten:
        sleutel = (charge.payable_type, charge.payable_id)
        if sleutel not in volgorde:
            volgorde[sleutel] = len(groepen)
            groepen.append({"kaarten": [], "records": []})
        groep = groepen[volgorde[sleutel]]
        groep["kaarten"].append((charge, eigen_refunds))
        groep["records"].extend([charge] + eigen_refunds)

    for groep in groepen:
        groep["totaal"] = aggregate(groep["records"])
        groep["toon_totaal"] = len(groep["records"]) > 1
    return groepen


# ── Verrijkte betaalrecords voor scherm en export (#645 E, #635) ──────────────

def enriched_records(db: Session) -> list:
    """Alle betaalrecords met hun context: wie, waarvoor, welke bestelregels.

    Verving een lus die per record vijf losse queries deed (registratie →
    onderdeel → activiteit → items → producten). Bij veertig records waren dat
    ruim driehonderd queries voor één scherm; met htmx voel je dat rechtstreeks
    (#645). Nu wordt per soort entiteit één keer gebatcht geladen en daarna in
    dicts opgezocht — het aantal queries hangt niet meer van het aantal records af.

    De verrijking haalt bewust óók soft-deleted entiteiten op (`include_deleted`,
    #190): een betaling is een financieel feit en moet de bewaarde naam blijven
    tonen, niet "—". De records zelf volgen de gewone soft-delete-filter.
    """
    from sqlalchemy.orm import selectinload

    from app.domains.activities.api import (
        Activity, ActivitySubRegistration, Registration, RegistrationItem,
        compute_registration_total,
    )
    from app.domains.mdm.api import Member, MemberPerson, Person
    from app.domains.membership.api import Membership
    from app.domains.payment.schemas import EnrichedPaymentRecord

    def _q(model):
        return db.query(model).execution_options(include_deleted=True)

    records = (db.query(PaymentRecord)
               .options(selectinload(PaymentRecord.gateway_payment))
               .order_by(PaymentRecord.created_at.desc()).all())

    reg_ids = {r.payable_id for r in records if r.payable_type == "registration"}
    ms_ids = {r.payable_id for r in records if r.payable_type == "membership"}

    # Registraties mét items en producten in één keer: compute_registration_total
    # loopt over registration.items en elk item over zijn product.
    registraties = {}
    if reg_ids:
        registraties = {r.id: r for r in _q(Registration)
                        .options(selectinload(Registration.items)
                                 .selectinload(RegistrationItem.product),
                                 selectinload(Registration.person))
                        .filter(Registration.id.in_(reg_ids)).all()}
    activiteiten = {}
    onderdelen = {}
    if registraties:
        act_ids = {r.activity_id for r in registraties.values() if r.activity_id}
        comp_ids = {r.component_id for r in registraties.values() if r.component_id}
        if act_ids:
            activiteiten = {a.id: a for a in
                            _q(Activity).filter(Activity.id.in_(act_ids)).all()}
        if comp_ids:
            onderdelen = {c.id: c for c in _q(ActivitySubRegistration)
                          .filter(ActivitySubRegistration.id.in_(comp_ids)).all()}

    lidmaatschappen = {}
    hoofdlid_naam = {}
    if ms_ids:
        lidmaatschappen = {m.id: m for m in
                           _q(Membership).filter(Membership.id.in_(ms_ids)).all()}
        member_ids = {m.member_id for m in lidmaatschappen.values()}
        if member_ids:
            leden = {m.id for m in _q(Member).filter(Member.id.in_(member_ids)).all()}
            koppels = _q(MemberPerson).filter(
                MemberPerson.member_id.in_(leden),
                MemberPerson.relation_type == "HOOFDLID").all()
            personen = {}
            if koppels:
                personen = {p.id: p for p in _q(Person)
                            .filter(Person.id.in_({k.person_id for k in koppels})).all()}
            for koppel in koppels:
                persoon = personen.get(koppel.person_id)
                if persoon is not None:
                    hoofdlid_naam[koppel.member_id] = (
                        f"{persoon.first_name} {persoon.last_name}")

    resultaat = []
    for r in records:
        contact_name = description = None
        activity_id = component_id = component_name = membership_year = None
        reg_items: list = []

        if r.payable_type == "registration":
            reg = registraties.get(r.payable_id)
            if reg is not None:
                contact_name = reg.contact_name
                activity_id = reg.activity_id
                component_id = reg.component_id
                onderdeel = onderdelen.get(reg.component_id)
                component_name = onderdeel.name if onderdeel else None
                activiteit = activiteiten.get(reg.activity_id)
                if activiteit is not None:
                    description = activiteit.name
                    _totaal, regels = compute_registration_total(reg)
                    reg_items = [{"product_name": regel["name"],
                                  "quantity": regel["quantity"],
                                  "unit_price": float(regel["unit_price"]),
                                  "subtotal": float(regel["subtotal"])}
                                 for regel in regels]
        elif r.payable_type == "membership":
            # payable_id is de Membership.id (niet de Member.id) — het jaar komt
            # van het lidmaatschap, de naam van het hoofdlid van dat gezin (#141).
            ms = lidmaatschappen.get(r.payable_id)
            description = f"Lidmaatschap {ms.year}" if ms else "Lidmaatschap"
            membership_year = ms.year if ms else None
            if ms is not None:
                contact_name = hoofdlid_naam.get(ms.member_id)

        resultaat.append(EnrichedPaymentRecord(
            id=r.id, payable_type=r.payable_type, payable_id=r.payable_id,
            activity_id=activity_id, component_id=component_id,
            component_name=component_name, membership_year=membership_year,
            items=reg_items, amount=r.amount, amount_paid=r.amount_paid,
            method=r.method, status=r.status, type=r.type,
            refund_of_id=r.refund_of_id, note=r.note, paid_at=r.paid_at,
            checkout_url=r.gateway_payment.checkout_url if r.gateway_payment else None,
            structured_communication=r.structured_communication,
            created_at=r.created_at, description=description,
            contact_name=contact_name,
        ))
    return resultaat


# ── Schermbewerkingen: één handeling van de penningmeester (#635 I) ───────────
# De functies hierboven zijn bouwstenen: ze muteren en flushen, maar committen
# niet, want `reconcile_charges` roept er meerdere na elkaar aan en die reeks moet
# in één transactie passen.
#
# Wat de penningmeester op het scherm doet, is één handeling — en die hoort hier
# te eindigen, inclusief de commit. Voorheen stond dat in de route, samen met
# regels die daar niet horen: het omdraaien van het teken bij een terugbetaling en
# de bovengrens erop stonden in `payment/ui.py`, terwijl ze bepalen hoeveel geld er
# terugvloeit.

class BetalingFout(ValueError):
    """Een invoerfout die het scherm als melding toont. Geen HTTPException: de
    service kent geen HTTP, en de route bepaalt zelf de statuscode."""


def _bedrag(tekst: str | None) -> Decimal | None:
    """Een ingetypt bedrag, of None als er niets ingevuld is.

    Komma én punt zijn toegestaan: op een Belgisch toetsenbord typ je een komma,
    en dat mag geen foutmelding opleveren.
    """
    if not (tekst or "").strip():
        return None
    try:
        return Decimal(tekst.replace(",", "."))
    except (InvalidOperation, AttributeError):
        raise BetalingFout("Ongeldig bedrag.")


def bevestig_betaling(db: Session, record_id: str, *, note: str | None = None,
                      amount_paid: str | None = None, actor: str | None = None):
    """"Bevestig betaald", met optioneel het effectief ontvangen bedrag (#455)."""
    try:
        record = confirm_manual_payment(db, record_id, (note or "").strip() or None,
                                        actor=actor, amount_paid=_bedrag(amount_paid))
    except ValueError as exc:
        db.rollback()
        raise BetalingFout(str(exc)) from exc
    db.commit()
    return record


def registreer_terugbetaling(db: Session, record_id: str, *, amount: str,
                             note: str | None = None, actor: str | None = None):
    """"Terugbetaling registreren" (#617-2b).

    `settled=False`: de terugbetaling ontstaat met een terug te betalen bedrag en
    een leeg uitbetaald bedrag, precies zoals een vordering ontstaat met een te
    betalen bedrag en niets ontvangen. Aanmaken en afboeken zijn twee stappen. De
    service-default blijft True voor andere aanroepers.
    """
    bedrag = _bedrag(amount)
    if bedrag is None:
        raise BetalingFout("Ongeldig bedrag.")
    try:
        refund = create_refund(db, record_id, bedrag, note=(note or "").strip() or None,
                               actor=actor, settled=False)
    except ValueError as exc:
        db.rollback()
        raise BetalingFout(str(exc)) from exc
    db.commit()
    return refund


def bewerk_betaling(db: Session, record_id: str, *, status: str | None = None,
                    amount_paid: str | None = None, note: str | None = None,
                    actor: str | None = None):
    """Status, ontvangen bedrag en opmerking in één keer (#515).

    Het minteken op een terugbetaling is een boekhoudkundige interne conventie —
    zo kloppen de sommen — en dat hoort niemand in te typen. De penningmeester
    moest letterlijk "-40.00" invoeren, want "40.00" werd geweigerd (#617-2c). Het
    scherm toont mét teken, je voert in zonder, en hier draait het om. De grens
    (nooit meer dan het terug te betalen bedrag) hoort bij diezelfde regel.
    """
    record = db.query(PaymentRecord).filter(PaymentRecord.id == record_id).first()
    if record is None:
        raise LookupError("Betaling niet gevonden.")

    bedrag = _bedrag(amount_paid)
    if bedrag is not None and record.type == "refund":
        grens = abs(_bedrag(str(record.amount)) or Decimal("0"))
        if abs(bedrag) > grens:
            raise BetalingFout(
                f"Meer dan het terug te betalen bedrag (€ {grens:.2f}).")
        bedrag = -abs(bedrag)

    try:
        edit_payment_record(db, record_id, status=(status or "").strip() or None,
                            amount_paid=bedrag, note=(note or "").strip() or None,
                            actor=actor)
    except ValueError as exc:
        db.rollback()
        raise BetalingFout(str(exc)) from exc
    db.commit()
    return record


def ververs_betaalstatus(db: Session, record_id: str, *, actor: str | None = None):
    """De status bij de betaalprovider ophalen en toepassen — de handmatige
    tegenhanger van de webhook (#455)."""
    try:
        record = refresh_record_status(db, record_id, actor=actor)
    except ValueError as exc:
        db.rollback()
        raise BetalingFout(str(exc)) from exc
    db.commit()
    return record


def zet_betaalstatus(db: Session, record_id: str, status: str, *,
                     note: str | None = None, actor: str | None = None):
    """Vrije statuscorrectie door de penningmeester (#455)."""
    try:
        record = set_payment_status(db, record_id, (status or "").strip(), actor=actor,
                                    note=(note or "").strip() or None)
    except ValueError as exc:
        db.rollback()
        raise BetalingFout(str(exc)) from exc
    db.commit()
    return record


def verwijder_betaling(db: Session, record_id: str, *, note: str | None = None,
                       actor: str | None = None):
    """Soft-delete: uit het saldo, maar bewaard als financieel feit (#455).
    Corrigeert ook een foute terugbetaling."""
    try:
        record = void_payment_record(db, record_id, actor=actor,
                                     note=(note or "").strip() or None)
    except ValueError as exc:
        db.rollback()
        raise BetalingFout(str(exc)) from exc
    db.commit()
    return record
