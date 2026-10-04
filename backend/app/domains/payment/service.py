from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Optional, Tuple

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.audit.api import snapshot_payment_record
from app.domains.mdm.api import CONTACT, MemberPerson, PaymentMethod, Person, RelationType
from app.domains.membership.api import Membership
from app.kernel.codes import code_of

from .models import PayableType, PaymentError, PaymentRecord, PaymentStatus, PaymentType

# Semantische history-actie per (interne) gateway-status, zodat de tijdlijn
# meteen toont wat de gateway/admin-refresh meldde i.p.v. een generiek label.
_GATEWAY_ACTION = {
    PaymentStatus.PAID: "payment_paid",
    PaymentStatus.FAILED: "payment_failed",
    PaymentStatus.CANCELLED: "payment_cancelled",
    PaymentStatus.PENDING: "payment_pending",
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


def create_payment_record(
    db: Session,
    payable_type: PayableType | str,
    payable_id: int,
    amount: Decimal,
    method: PaymentMethod | str,
    redirect_url: Optional[str] = None,
    description: Optional[str] = None,
    audit_source: str = "system",
    audit_actor: Optional[str] = None,
) -> PaymentRecord:
    # Convert at the boundary (CR-12 phase 1). This function is called from four
    # domains and from the tests, with a code or with a member; inside the
    # function it is always a member, so the comparisons below do not depend on
    # the caller. An unknown value fails here, naming the list, rather than
    # further down on the foreign key.
    payable_type = PayableType(payable_type)
    method = PaymentMethod(method)
    if method == PaymentMethod.ONLINE:
        from app.domains.payment.gateway_service import create_payment as gw_create

        gp = gw_create(
            db=db,
            amount=amount,
            # `.value` (#1279): `payable_type` is a member here, and a plain
            # Enum in an f-string reads `PayableType.MEMBERSHIP`.
            description=description or f"{payable_type.value} #{payable_id}",
            redirect_url=redirect_url or "",
            # The code, not the member: this goes to the gateway as JSON and
            # comes back that way in the webhook. An enum is not serialisable,
            # and besides, it is their field, not ours.
            metadata={"payable_type": payable_type.value, "payable_id": payable_id},
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
            status=PaymentStatus.PENDING,
        )
        # Overschrijving: genereer een unieke gestructureerde mededeling (OGM) zodat
        # de inschrijver met referentie betaalt en de penningmeester kan reconciliëren (#157).
        if method == PaymentMethod.TRANSFER:
            from sqlalchemy import text

            from app.domains.payment.structured_communication import (
                generate_structured_communication,
            )

            seq = db.execute(text("SELECT nextval('payment_ogm_seq')")).scalar()
            record.structured_communication = generate_structured_communication(int(seq))

    db.add(record)
    db.flush()
    snapshot_payment_record(
        db,
        record,
        operation="insert",
        action="payment_created",
        source=audit_source,
        actor=audit_actor,
    )
    return record


def handle_gateway_update(
    db: Session,
    gateway_payment_id: str,
    new_status: PaymentStatus | str,
    source: str = "mollie",
    actor: Optional[str] = None,
) -> None:
    """Called by gateway webhook handler to propagate status to PaymentRecord.

    Idempotent en concurrency-veilig (#91): we vergrendelen de betrokken
    PaymentRecord-rij(en) (SELECT ... FOR UPDATE) zodat gelijktijdige/herhaalde
    webhooks serialiseren. Een herhaalde 'paid' is een no-op (status ongewijzigd →
    `continue`) en stempelt paid_at/amount_paid niet opnieuw. Een DB-unieke index
    op gateway_payment_id garandeert bovendien max. één record per gateway-betaling."""
    # The gateway delivers a string; convert it here, at the boundary. Without
    # that, `record.status == new_status` below would compare a member with a
    # string — always false, so *every* webhook a silent no-op.
    new_status = PaymentStatus(new_status)
    records = (
        db.query(PaymentRecord)
        .filter(PaymentRecord.gateway_payment_id == gateway_payment_id)
        .with_for_update()
        .all()
    )
    for record in records:
        if record.status == new_status:
            continue
        event = None
        if new_status == PaymentStatus.PAID and record.paid_at is None:
            event = record.mark_paid(
                None, at=datetime.now(timezone.utc), source=source, actor=actor
            )
        else:
            record.status = new_status
            if new_status == PaymentStatus.PAID:
                event = record.received(source=source, actor=actor)
        snapshot_payment_record(
            db,
            record,
            operation="update",
            action=_GATEWAY_ACTION.get(new_status, "payment_status_changed"),
            source=source,
            actor=actor,
        )
        # CR-13 phase 2: consumers react to the money without this component calling
        # them — `membership` activates a membership (#113), `workflow` looks at the
        # workbench now. In the same transaction; the idempotent no-op above keeps a
        # repeated webhook from publishing twice.
        if event is not None:
            _publish(db, event)


def _publish(db: Session, event) -> None:
    from app.kernel.events import publish

    publish(event, db)


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
    # The record's own rule since CR-13 phase 2, asked before anything changes.
    if amount_paid is not None:
        record.validate_booking(amount_paid)
    # Refund-bewuste invariant (#517): een charge die al (deels) terugbetaald is,
    # mag zijn ontvangen bedrag NIET stil verlaagd krijgen — dat maakt de netto-
    # positie incoherent met de reeds uitbetaalde terugbetaling (bv. €30 ontvangen,
    # €10 terug, dan "€20 betaald" → net €10 i.p.v. €20). `create_refund` bewaakt de
    # andere kant al; dit is de omgekeerde weg. Blokkeren i.p.v. stil overschrijven;
    # de penningmeester corrigeert dan via de terugbetaling.
    if amount_paid is not None and record.type == PaymentType.CHARGE:
        refunds = [
            r
            for r in get_records_for(db, record.payable_type, record.payable_id)
            if r.type == PaymentType.REFUND
        ]
        total_refunded = -amount_received(refunds)
        if total_refunded > 0:
            current = (
                Decimal(str(record.amount_paid)) if record.amount_paid is not None else Decimal("0")
            )
            # Enkel een VERLAGING van het reeds-ontvangen bedrag van deze charge is
            # incoherent na een refund; een nieuwe/hogere betaling (bv. een partieel
            # betaalde open charge na een eerdere bestelverlaging) blijft toegestaan.
            if amount_paid < current:
                raise ValueError(
                    "Deze betaling is al (deels) terugbetaald — je kunt het ontvangen "
                    "bedrag niet verlagen zonder de terugbetaling te verrekenen. "
                    "Corrigeer eerst de terugbetaling."
                )
    # #199, #720: the record books what came in and lets the amounts decide paid or
    # not (`PaymentRecord.mark_paid`). Before phase 2 this function did it itself,
    # and #720 found it setting "paid" on € 10,00 of € 35,00.
    event = record.mark_paid(
        amount_paid, at=datetime.now(timezone.utc), source="admin_manual", actor=actor
    )
    if note:
        record.note = note
    db.flush()
    snapshot_payment_record(
        db,
        record,
        operation="update",
        action="payment_manually_confirmed",
        source="admin_manual",
        actor=actor,
    )
    # A membership is activated by `membership` on this event, and only when the
    # amount covers the charge (#143, #720).
    _publish(db, event)
    return record


def family_payables(db: Session, family_id: int) -> set:
    """(payable_type, payable_id)-paren van één gezin (golf 9, #913): de
    lidmaatschappen van het gezin plus de inschrijvingen van zijn personen —
    op person_id, én op e-mailadres voor gastinschrijvingen (dezelfde regel
    als de audit-resolver). include_deleted: een betaling is een financieel
    feit (#190), dus ook geschrapte lidmaatschappen/inschrijvingen tellen."""
    from sqlalchemy import or_

    from app.domains.activities.api import Registration
    from app.domains.mdm.api import ContactDetail

    def q(model):
        return db.query(model).execution_options(include_deleted=True)

    ms_ids = [r[0] for r in q(Membership.id).filter(Membership.member_id == family_id).all()]
    person_ids = [
        r[0] for r in q(MemberPerson.person_id).filter(MemberPerson.member_id == family_id).all()
    ]
    emails = [
        r[0].strip().lower()
        for r in q(ContactDetail.value)
        .filter(
            ContactDetail.person_id.in_(person_ids or [0]),
            ContactDetail.contact_type_code == CONTACT.EMAIL,
        )
        .all()
        if r[0]
    ]
    voorwaarden = []
    if person_ids:
        voorwaarden.append(Registration.person_id.in_(person_ids))
    if emails:
        voorwaarden.append(func.lower(Registration.contact_email).in_(emails))
    reg_ids = (
        [r[0] for r in q(Registration.id).filter(or_(*voorwaarden)).all()] if voorwaarden else []
    )
    return {(PayableType.MEMBERSHIP, i) for i in ms_ids} | {
        (PayableType.REGISTRATION, i) for i in reg_ids
    }


def count_records_for_family(db: Session, family_id: int) -> int:
    """Het getal op de Betalingen-tab van de gezinspagina — via dezelfde
    payable-verzameling, één COUNT."""
    from sqlalchemy import tuple_

    paren = family_payables(db, family_id)
    if not paren:
        return 0
    return (
        db.query(PaymentRecord)
        .filter(tuple_(PaymentRecord.payable_type, PaymentRecord.payable_id).in_(list(paren)))
        .count()
    )


def count_registration_records_by_activity(db: Session, activity_id: int) -> int:
    """Idem, maar per activiteit en als één COUNT met subquery (golf 8): de
    recordpagina mag niet schalen met het aantal inschrijvingen (#651)."""
    from app.domains.activities.api import Registration

    sub = db.query(Registration.id).filter(Registration.activity_id == activity_id)
    return (
        db.query(PaymentRecord)
        .filter(
            PaymentRecord.payable_type == PayableType.REGISTRATION,
            PaymentRecord.payable_id.in_(sub),
        )
        .count()
    )


def registration_payment_states(db: Session, registration_ids) -> dict[int, dict]:
    """Per registration what its bookings say together (CR-11 K6, #1560): the
    amounts and one state — ``"open"`` while a booking still has money to move
    (the same test as the Betalingen list's *Openstaand*, `matches_zicht`),
    ``"settled"`` when it has bookings and none is open. A registration without
    a booking (nothing to pay) is not in the result.

    One query for the whole list: the Inschrijvingen tab shows a state per row
    and may not ask per row.
    """
    ids = list(registration_ids)
    if not ids:
        return {}
    records = (
        db.query(PaymentRecord)
        .filter(
            PaymentRecord.payable_type == PayableType.REGISTRATION,
            PaymentRecord.payable_id.in_(ids),
        )
        .all()
    )
    per_registration: dict[int, list] = {}
    for record in records:
        per_registration.setdefault(record.payable_id, []).append(record)
    states = {}
    for registration_id, own in per_registration.items():
        live = [r for r in own if not _is_lege_vordering(r)]
        if not live:
            continue
        states[registration_id] = {
            **aggregate(live),
            "state": "open" if any(matches_zicht(r, "openstaand") for r in live) else "settled",
        }
    return states


def selection_count(
    db: Session, *, context: str = "all", view: str = "alle", activity_id: int | None = None
) -> int:
    """How many bookings the payments list holds for this filter (CR-11 K8, #1562):
    the size of the selection the Assistent panel names ("over 8 openstaande
    betalingen"). Counted by the list's own filter (`filter_records`), so the
    line and the screen cannot differ; **bookings**, not the registration groups
    the toolbar counts — a booking is the row a report counts."""
    from app.domains.activities.api import registration_ids_for

    payables = None
    if activity_id is not None:
        payables = {(PayableType.REGISTRATION, i) for i in registration_ids_for(db, activity_id)}
    return len(filter_records(enriched_records(db), context=context, zicht=view, payables=payables))


def registration_balance_by_activity(db: Session, activity_id: int) -> Decimal:
    """What is still open on an activity's registrations, signed: the sum of
    every booking's amount minus what was booked as received — the same sum as
    `aggregate(...)["saldo"]` over those records (CR-11 K6, #1560: "Openstaand"
    on the record's summary card). One aggregate row, like the count beside it:
    the record page may not scale with the number of registrations (#651)."""
    from sqlalchemy import func

    from app.domains.activities.api import Registration

    sub = db.query(Registration.id).filter(Registration.activity_id == activity_id)
    due, paid = (
        db.query(
            func.coalesce(func.sum(PaymentRecord.amount), 0),
            func.coalesce(func.sum(PaymentRecord.amount_paid), 0),
        )
        .filter(
            PaymentRecord.payable_type == PayableType.REGISTRATION,
            PaymentRecord.payable_id.in_(sub),
        )
        .one()
    )
    return _bedrag(due) - _bedrag(paid)


def open_refund_amount(db: Session, payable_type: PayableType | str, payable_id: int) -> Decimal:
    """What is waiting to be refunded on this payable, as a positive amount (#1494):
    the refunds not confirmed yet (`amount_paid` empty). A screen says it after an
    order went down, so the board sees the money it now owes."""
    total = Decimal("0")
    for record in get_records_for(db, payable_type, payable_id):
        if code_of(record.type) == "refund" and record.amount_paid is None:
            total += -Decimal(str(record.amount))
    return total


def get_records_for(
    db: Session, payable_type: PayableType | str, payable_id: int
) -> list[PaymentRecord]:
    return (
        db.query(PaymentRecord)
        .filter(
            PaymentRecord.payable_type == payable_type,
            PaymentRecord.payable_id == payable_id,
        )
        .all()
    )


def amount_received(records) -> Decimal:
    """What came in on a set of payment records: the sum of what was booked, a
    refund counting negative, a record with nothing booked as 0.

    The one place this sum is made (CR-13 phase 2, one owner per derived value):
    the balance of a registration, the reconciliation of an order, the totals of a
    group of cards and the refund check each made it themselves.
    """
    return sum(
        (Decimal(str(r.amount_paid)) for r in records if r.amount_paid is not None),
        Decimal("0"),
    )


def net_paid(db: Session, payable_type: PayableType | str, payable_id: int) -> Decimal:
    """Netto ontvangen bedrag op een payable: som van amount_paid over alle
    records (charges positief, refunds negatief). Een nog niet betaalde charge
    (amount_paid is None) telt als 0."""
    return amount_received(get_records_for(db, payable_type, payable_id))


def create_refund(
    db: Session,
    charge_record_id: str,
    amount: Decimal,
    *,
    note: Optional[str] = None,
    method: PaymentMethod | str = PaymentMethod.TRANSFER,
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
    if charge.type != PaymentType.CHARGE:
        raise ValueError("Een terugbetaling kan enkel een 'charge'-record terugdraaien.")

    refund_amount = Decimal(str(amount))
    if refund_amount <= 0:
        raise ValueError("Het terug te betalen bedrag moet strikt positief zijn.")

    available = net_paid(db, charge.payable_type, charge.payable_id)
    if refund_amount > available:
        # #723: deze zin komt écht op het scherm, dus de bedragen staan er als geld
        # en niet kaal. #735: met een komma, via dezelfde helper als de sjablonen —
        # anders schrijft de melding het bedrag anders dan de kaart erboven.
        from app.kernel.geld import bedrag

        raise ValueError(
            f"Kan niet meer terugbetalen (€ {bedrag(refund_amount)}) dan er netto "
            f"ontvangen is (€ {bedrag(available)})."
        )

    record = PaymentRecord(
        payable_type=charge.payable_type,
        payable_id=charge.payable_id,
        amount=-refund_amount,
        amount_paid=(-refund_amount if settled else None),
        method=method,
        status=(PaymentStatus.PAID if settled else PaymentStatus.PENDING),
        type=PaymentType.REFUND,
        refund_of_id=charge.id,
        note=note,
        paid_at=(datetime.now(timezone.utc) if settled else None),
    )
    db.add(record)
    db.flush()
    snapshot_payment_record(
        db,
        record,
        operation="insert",
        action="payment_refunded",
        source=source,
        actor=actor,
    )
    # #705: een openstaande terugbetaling hoort meteen op de werkbank te staan, niet
    # pas bij de volgende uurlijkse ronde. Since CR-13 phase 2 through an event:
    # `workflow` subscribes and advances the sweep — it does not make the task
    # itself, the title is the idempotency key (#705).
    if not settled:
        from app.kernel.contracts.payment import RefundDue

        _publish(
            db,
            RefundDue(
                refund_record_id=record.id,
                payable_type=code_of(record.payable_type) or "",
                payable_id=record.payable_id,
                amount=str(record.amount),
            ),
        )
    return record


#: CR-12 phase 1: a second list with the same four values as the enum used to
#: stand here. Two places for one fact, and the enum is the source —
#: `PaymentStatus(x)` rejects what is not in it, with the same message for
#: every caller.
def _as_status(status) -> PaymentStatus:
    """A string or a member to the member, with a readable rejection."""
    try:
        return PaymentStatus(status)
    except ValueError:
        raise ValueError(f"Ongeldige status '{status}'.") from None


def refresh_record_status(
    db: Session, record_id: str, actor: Optional[str] = None
) -> PaymentRecord:
    """Ververs de status van een online betaling bij de provider (Mollie) en pas
    ze toe op de PaymentRecord(s) — de handmatige tegenhanger van de webhook
    (#455). Enkel zinvol voor een record met een gekoppelde gateway-betaling."""
    from app.domains.payment.gateway_service import refresh_payment_status

    record = db.query(PaymentRecord).filter(PaymentRecord.id == record_id).first()
    if not record:
        raise ValueError(f"PaymentRecord {record_id} not found")
    # One rule for both ways in (CR-13 phase 2): the JSON route had its own copy,
    # with its own words; the screen's message is the one the treasurer knows.
    if record.method != PaymentMethod.ONLINE or not record.gateway_payment_id:
        raise PaymentError("Deze betaling heeft geen online (Mollie) betaling om te verversen.")
    gp = refresh_payment_status(db, record.gateway_payment_id)
    # 'needs_review' (bedrag-mismatch, #92) niet automatisch als betaald boeken.
    # `gp.status` is the provider's word, a plain string (a `GatewayPayment` column
    # without a code table, CR-12 §B4.10); `_GATEWAY_ACTION` is keyed by members. A
    # string is never a member, so this test was always false and the treasurer's
    # "Ververs" applied nothing — found in CR-13 phase 2, when the JSON route, which
    # had worked around it, started to ask this function too.
    try:
        status = PaymentStatus(gp.status)
    except ValueError:
        status = None
    if status in _GATEWAY_ACTION:
        handle_gateway_update(db, gp.id, status, source="admin_refresh", actor=actor)
    # A flush, not a refresh (#1249): `handle_gateway_update` changes this same object
    # through the identity map and does not flush. A refresh reloaded the row from the
    # database and threw the booking away — unless a subscriber happened to query and
    # autoflush first, which the membership handler does and a registration has none.
    db.flush()
    return record


def set_payment_status(
    db: Session,
    record_id: str,
    status: PaymentStatus | str,
    actor: Optional[str] = None,
    note: Optional[str] = None,
) -> PaymentRecord:
    """Vrije status-correctie door de penningmeester (#455). Enkel binnen de
    gekende set; bij 'paid' wordt (als nog niet betaald) paid_at/amount_paid gezet,
    bij elke andere status worden die gewist zodat het bedrag niet meer meetelt in
    het saldo. Alles met een history-snapshot voor de audittrail."""
    wanted = _as_status(status)
    record = db.query(PaymentRecord).filter(PaymentRecord.id == record_id).first()
    if not record:
        raise ValueError(f"PaymentRecord {record_id} not found")
    # CR-13 phase 2: "paid" books money through the record, so the amounts decide
    # (#720) — a record that is only partly paid stays partly paid; nothing booked
    # yet books the full amount, as before. Any other status forgets what came in.
    event = None
    if wanted is PaymentStatus.PAID:
        event = record.mark_paid(
            record.amount_paid,
            at=record.paid_at or datetime.now(timezone.utc),
            source="admin_manual",
            actor=actor,
        )
    else:
        record.cancel(wanted)
    if note:
        record.note = note
    db.flush()
    snapshot_payment_record(
        db,
        record,
        operation="update",
        action="payment_status_edited",
        source="admin_manual",
        actor=actor,
    )
    if event is not None:
        _publish(db, event)
    return record


def edit_payment_record(
    db: Session,
    record_id: str,
    *,
    status: PaymentStatus | str | None = None,
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
            raise ValueError(f"Betaald bedrag ({amount_paid}) moet tussen {lo} en {hi} liggen.")
    if status is not None and _as_status(status) is PaymentStatus.PAID:
        return confirm_manual_payment(db, record_id, note, actor=actor, amount_paid=amount_paid)
    if status is not None:
        record.status = _as_status(status)
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
        db,
        record,
        operation="update",
        action="payment_updated",
        source="admin_update",
        actor=actor,
    )
    return record


def void_payment_record(
    db: Session, record_id: str, actor: Optional[str] = None, note: Optional[str] = None
) -> PaymentRecord:
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
        db,
        record,
        operation="delete",
        action="payment_voided",
        source="admin_manual",
        actor=actor,
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
    records = get_records_for(db, PayableType.REGISTRATION, registration.id)
    total_paid = amount_received(records)
    total_refunded = -amount_received(r for r in records if r.type == PaymentType.REFUND)
    return {
        "total_due": total_due,
        "total_paid": total_paid,
        "total_refunded": total_refunded,
        "balance": total_due - total_paid,
    }


def reconcile_charges(
    db: Session,
    payable_type: PayableType | str,
    payable_id: int,
    total_due,
    *,
    audit_actor: Optional[str] = None,
    source: str = "order-edit",
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

    net_paid = amount_received(records)
    paid_charge = None
    for r in records:
        if r.amount_paid is None:
            # Open (onbetaalde) post → weg; het openstaande wordt herleid tot één post.
            snapshot_payment_record(
                db,
                r,
                operation="delete",
                action="order_reconciled",
                source=source,
                actor=audit_actor,
            )
            soft_delete(r)
        elif Decimal(str(r.amount_paid)) == 0:
            # CR-13 phase 2, (b) of #1249 (Koen, 28 September 2026): a record on which
            # nothing came in is removed, not closed on 0,00 — closing it would write a
            # charge or refund of nothing, the trap #673 named, which the sign rule
            # refuses. Soft-deleted with `amount` left as it was, so no 0,00 is ever
            # written; it leaves the payment list with a history row.
            snapshot_payment_record(
                db,
                r,
                operation="delete",
                action="order_reconciled",
                source=source,
                actor=audit_actor,
            )
            soft_delete(r)
        else:
            # Betaalde post = waarheid; sluit een partieel betaalde charge op zijn
            # effectief betaalde bedrag.
            if Decimal(str(r.amount)) != Decimal(str(r.amount_paid)):
                r.amount = r.amount_paid
                snapshot_payment_record(
                    db,
                    r,
                    operation="update",
                    action="order_reconciled",
                    source=source,
                    actor=audit_actor,
                )
            if r.type == PaymentType.CHARGE and Decimal(str(r.amount_paid)) > 0:
                paid_charge = r

    outstanding = total_due - net_paid
    if outstanding > 0:
        # Eén openstaande charge voor het volledige openstaande bedrag (met OGM).
        create_payment_record(
            db,
            payable_type,
            payable_id,
            amount=outstanding,
            method=PaymentMethod.TRANSFER,
            audit_source=source,
            audit_actor=audit_actor,
        )
    elif outstanding < 0 and paid_charge is not None:
        # Te veel ontvangen → één terugbetaling, met de methode van de betaalde charge.
        method = (
            paid_charge.method
            if paid_charge.method in (PaymentMethod.TRANSFER, PaymentMethod.CASH)
            else PaymentMethod.TRANSFER
        )
        # Verplichting, geen voldongen feit: de penningmeester bevestigt de
        # effectieve terugstorting (#216). Daarom pending, niet meteen 'paid'.
        create_refund(
            db,
            paid_charge.id,
            -outstanding,
            method=method,
            note=refund_note,
            actor=audit_actor,
            source=source,
            settled=False,
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

    reconcile_charges(
        db,
        PayableType.REGISTRATION,
        registration.id,
        compute_registration_total(registration)[0],
        audit_actor=audit_actor,
    )


# ── Wat het betalingenscherm en de export samen nodig hebben (#635 punt 4/9) ──
# Filter, aggregatie, kaartgroepering en afgeleide status stonden in de UI-route
# (payment/ui.py) en, half, nog eens in exports.py. Ze waren al uit elkaar gelopen:
# het scherm kende `failed`/`cancelled` en vrije zoektekst, de export niet; de
# export eiste payable_type == "registration" bij een onderdeelfilter, het scherm
# niet. Wie op het scherm filterde en dan exporteerde, kreeg iets anders. Eén
# implementatie, twee ingangen.

_SALDO_DREMPEL = Decimal("0.001")  # afrondingsruis is geen openstaand saldo


def _bedrag(waarde) -> Decimal:
    return Decimal(str(waarde or 0))


def matches_filter(
    record,
    *,
    context: str = "all",
    status: str = "all",
    q: str = "",
    openstaand: bool = False,
    membership_year=None,
    component_id=None,
) -> bool:
    """Hoort dit record bij het gekozen filter?

    `membership_year`/`component_id` mogen expliciet meegegeven worden voor
    aanroepers die ze zelf afleiden (de export verrijkt de rauwe records); anders
    komen ze van het record zelf, zoals het scherm ze krijgt.

    Volgorde is betekenisvol: de zoekterm staat vóór de andere filters, zodat je
    binnen het gekozen filter zoekt en niet erbuiten (#591).
    """
    jaar = (
        membership_year if membership_year is not None else getattr(record, "membership_year", None)
    )
    comp = component_id if component_id is not None else getattr(record, "component_id", None)

    term = (q or "").strip().lower()
    if term:
        velden = (
            getattr(record, "contact_name", None),
            getattr(record, "structured_communication", None),
            getattr(record, "description", None),
            getattr(record, "component_name", None),
        )
        if not any(term in (waarde or "").lower() for waarde in velden):
            return False

    if context == "membership" and record.payable_type != PayableType.MEMBERSHIP:
        return False
    if context.startswith("year-"):
        if record.payable_type != PayableType.MEMBERSHIP or jaar != int(context[5:]):
            return False
    if context.startswith("comp-"):
        # payable_type meecontroleren (kwam uit de export-variant): een
        # component_id hoort per definitie bij een inschrijving.
        if record.payable_type != PayableType.REGISTRATION or comp != int(context[5:]):
            return False

    # #669: "openstaand" is een AFGELEIDE toestand (amount != amount_paid), de
    # dropdown gaat over de statuskolom. Twee soorten predicaat in één keuzelijst
    # betekende dat je er maar één tegelijk kon nemen — "openstaande posten onder
    # de mislukte betalingen" kon niet. Nu combineren ze met EN. De oude waarde
    # blijft werken, zodat een bestaande link of export-URL niet stil iets anders
    # gaat tonen.
    if openstaand or status == "openstaand":
        if not saldo_open(record):
            return False
    if status in {m.value for m in PaymentStatus}:
        # `.value`, because `status` arrives from the filter bar as a string.
        # Without that step this compares a member with a string: always false,
        # so *every* status filter would give an empty list — silently, without
        # an error.
        return record.status.value == status
    return True


def saldo_open(record) -> bool:
    """Staat er op dit record nog saldo open?

    Openstaand komt uit het saldo, niet uit de statuskolom: betaald = waarheid
    (#198). Op de ABSOLUTE waarde (#668): een terugbetaling heeft een NEGATIEF
    bedrag, dus de eenrichtingsvergelijking liet veertien openstaande refunds
    (en elke te veel betaalde vordering) uit het filter vallen. Gedeeld door
    matches_filter en de zichten (golf 10, #913) — twee eigen kopieën van deze
    drempeltest zouden precies de duplicatiefout uit CLAUDE.md zijn.
    """
    return abs(_bedrag(record.amount) - _bedrag(record.amount_paid)) > _SALDO_DREMPEL


ZICHTEN = ("alle", "openstaand", "betaald", "terugbetaald")


def matches_zicht(record, zicht: str) -> bool:
    """Golf 10 (#913): de statustabs boven de betalingenlijst.

    Een zicht is een AFGELEIDE doorsnede naast de statuskolom — het combineert
    met EN met de andere filters, precies de #669-les. 'openstaand' deelt de
    saldotest met het oude schakelaar-erfgoed; 'betaald' is vereffend volgens
    derived_status; 'terugbetaald' is het refund-type, ongeacht status.
    """
    if zicht == "openstaand":
        return saldo_open(record)
    if zicht == "betaald":
        return derived_status(record) == "paid"
    if zicht == "terugbetaald":
        return getattr(record, "type", None) == PaymentType.REFUND
    return True


def apply_zicht(records, zicht: str) -> list:
    """Het zicht toepassen op een al gefilterde set. Los aanroepbaar zodat het
    scherm eerst zonder zicht kan tellen (de tab-aantallen) en daarna dezelfde
    doorsnede toont die filter_records en de export maken."""
    if zicht in ("", "alle"):
        return list(records)
    return [r for r in records if matches_zicht(r, zicht)]


def count_zichten(records) -> dict:
    """Aantal records per zicht, over de zicht-loze (wel gefilterde) set —
    de getallen op de tabs."""
    return {z: sum(1 for r in records if matches_zicht(r, z)) for z in ZICHTEN}


def filter_records(
    records,
    *,
    context: str = "all",
    status: str = "all",
    q: str = "",
    openstaand: bool = False,
    record_id: str = "",
    registration_id: str = "",
    payables: set | None = None,
    zicht: str = "alle",
) -> list:
    """#704: `record_id` toont één betaling, ongeacht de andere filters.

    Een werkbanktaak linkt hierheen. Bewust een FILTER en geen anker: de lijst wordt
    gefilterd, dus een anker kan naar een kaart wijzen die op deze pagina niet
    gerenderd is — en dan landt de beheerder ergens zonder te zien waarom.

    De zoekterm (`q`) kon dit niet: die kijkt naar naam, mededeling, omschrijving en
    onderdeel, niet naar het id.

    `registration_id` (P13, golf 5 #913) is een SCOPE, geen filter: ze beperkt de
    verzameling tot de betalingen van één inschrijving, en de gewone filters werken
    daarbinnen. Het scherm toont er een zichtbare scope-regel bij — een onzichtbaar
    voorfilter is precies wat het patroon verbiedt.
    """
    scope = (registration_id or "").strip()
    if scope:
        records = [
            r
            for r in records
            if r.payable_type == PayableType.REGISTRATION and str(r.payable_id) == scope
        ]
    # Golf 8/9 (#913): recordSCOPES als payable-verzameling — activiteit (alleen
    # inschrijvingen) of gezin (inschrijvingen + lidmaatschappen). De aanroeper
    # lost het record op naar (payable_type, payable_id)-paren via de facades;
    # dit blijft een pure lijstfilter. Registration-only zou elk lidgeld van het
    # gezin laten vallen — vandaar paren en geen kale id-set.
    if payables is not None:
        records = [r for r in records if (r.payable_type, r.payable_id) in payables]
    doel = (record_id or "").strip()
    if doel:
        # #704 is een schijnwerper, geen filter: het zicht geldt er niet op.
        return [r for r in records if str(r.id) == doel]
    return apply_zicht(
        [
            r
            for r in records
            if matches_filter(r, context=context, status=status, q=q, openstaand=openstaand)
        ],
        zicht,
    )


def aggregate(records) -> dict:
    """Te betalen / ontvangen / saldo over een verzameling records."""
    due = sum((_bedrag(r.amount) for r in records), Decimal("0"))
    paid = amount_received(records)
    return {"due": due, "paid": paid, "saldo": due - paid}


def open_sides(records) -> dict:
    """What is still to be handled, as two sides that never net out (#1391, W1).

    Per record: a positive balance is money still to come in, a negative one is
    money still to go back (a pending refund, or an overpaid charge). They are
    summed apart on purpose: € 120 to receive and € 120 to refund is two things
    to do, and their net € 0 would read as "nothing to do" (CR-11 Q19). Each
    side also counts its bookings — since Koen's validation (1 October 2026)
    each side is a tile of its own.
    """
    to_receive = Decimal("0")
    to_refund = Decimal("0")
    receive_count = refund_count = 0
    for r in records:
        saldo = aggregate([r])["saldo"]
        if saldo > 0:
            to_receive += saldo
            receive_count += 1
        elif saldo < 0:
            to_refund -= saldo
            refund_count += 1
    return {
        "to_receive": to_receive,
        "to_refund": to_refund,
        "receive_count": receive_count,
        "refund_count": refund_count,
    }


def derived_status(record) -> str:
    """De status zoals ze op het scherm hoort te staan.

    De kolom `status` kent "Deels betaald" niet: dat is een *afgeleide* toestand
    (pending met een gedeeltelijke betaling) die de template zelf uitrekende — een
    regel die zo alleen in Jinja bestond en nergens testbaar was (#635 punt 9).
    Ook een terugbetaling die nog uitbetaald moet worden krijgt hier haar eigen
    naam, zodat het scherm niet op `type` én `status` hoeft te puzzelen.

    Waarden: paid · refund_due · partial · pending · failed · cancelled · <rauw>.
    """
    if record.status == PaymentStatus.PAID:
        return "paid"
    if (
        getattr(record, "type", None) == PaymentType.REFUND
        and record.status == PaymentStatus.PENDING
    ):
        return "refund_due"
    if record.status == PaymentStatus.PENDING:
        betaald = record.amount_paid
        if betaald is not None and _bedrag(betaald) != 0:
            return "partial"
        return "pending"
    # `code_of` and not `.value`: a test double may carry a bare string, and
    # an unknown value must come back here UNCHANGED — that is what "unknown
    # gateway status" means.
    return code_of(record.status) or ""


def deletion_refusal(record) -> Optional[str]:
    """Why this record may not be deleted, or None (#218, #617-2c).

    A payment on which money moved does not disappear: an online payment the
    provider confirmed as paid, and any record with money received or paid out. It
    is corrected with a refund. The one place of this rule since CR-13 phase 2 — the
    JSON route kept its own copy beside `may_delete`.
    """
    from app.i18n import _

    if record.method == PaymentMethod.ONLINE and record.status == PaymentStatus.PAID:
        return _("Een door Mollie betaalde online betaling kan niet verwijderd worden.")
    if record.amount_paid is not None and _bedrag(record.amount_paid) != 0:
        return _("Een betaling met een ontvangen/betaald bedrag kan niet verwijderd worden.")
    return None


def may_delete(record) -> bool:
    """Mag dit record verwijderd worden? — so the screen shows no button the rule
    refuses afterwards."""
    return deletion_refusal(record) is None


def delete_payment_record(
    db: Session, record_id: str, *, actor: Optional[str]
) -> Optional[PaymentRecord]:
    """Delete one record as a deliberate admin action (#167), or refuse (#218).

    Soft delete (#166), with a history row, so the financial fact stays in the
    history. None when there is no such record.
    """
    from app.soft_delete import soft_delete

    record = db.query(PaymentRecord).filter(PaymentRecord.id == record_id).first()
    if record is None:
        return None
    refusal = deletion_refusal(record)
    if refusal:
        raise PaymentError(refusal)
    snapshot_payment_record(
        db, record, operation="delete", action="payment_deleted", source="admin_manual", actor=actor
    )
    soft_delete(record)
    return record


def _is_lege_vordering(record) -> bool:
    """Een vordering van 0 waarop niets ontvangen is (#673).

    Zo eentje ontstaat bij het reconciliëren: een charge met `amount_paid = 0`
    wordt gesloten op zijn betaalde bedrag en houdt dan amount 0, status pending.
    Ze kan nooit betaald worden en blijft eeuwig als openstaande kaart staan — en
    ze is chronologisch vaak de EERSTE, dus zonder deze uitzondering wordt een
    kaart van 0,00 de hoofdkaart met de echte bedragen eronder.

    Verbergen is veilig omdat ze aan élk totaal exact 0 bijdraagt: het scherm toont
    minder, maar telt hetzelfde. Het record blijft in de databank staan — de
    geschiedenis van een betaling gooi je niet weg (#190) — en de export toont hem
    nog: dat is de financiële lijst, daar wil je de rij die bestaat.
    """
    if record.type == PaymentType.REFUND:
        return False
    betaald = record.amount_paid
    return _bedrag(record.amount) == 0 and (betaald is None or _bedrag(betaald) == 0)


def group_cards(records, alle_records=None) -> list[dict]:
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
    charges = [r for r in records if r.type != PaymentType.REFUND and not _is_lege_vordering(r)]
    refunds = [r for r in records if r.type == PaymentType.REFUND]

    per_charge: dict = {}
    for r in refunds:
        if r.refund_of_id:
            per_charge.setdefault(r.refund_of_id, []).append(r)
    charge_ids = {r.id for r in charges}

    # #668: een terugbetaling zonder haar charge zegt "10 terug te betalen" zonder
    # te zeggen waarvoor. Haal die ene charge erbij als CONTEXT — niet als
    # treffer. Ze telt niet mee in de totalen, want dan zou het filter liegen over
    # wat het toont. Alleen die ene charge, niet de hele groep: een inschrijving
    # kan er meerdere hebben en die horen hier niet.
    context_charges: dict = {}
    if alle_records is not None:
        buiten_beeld = {
            r.refund_of_id for r in refunds if r.refund_of_id and r.refund_of_id not in charge_ids
        }
        if buiten_beeld:
            context_charges = {r.id: r for r in alle_records if r.id in buiten_beeld}

    # Eén dict per kaart in plaats van een groeiende tuple: er zijn nu twee
    # eigenschappen die niets met elkaar te maken hebben (context, bijkomend), en
    # een vierde tuple-veld leest nergens meer.
    kaarten = [
        {"charge": r, "refunds": per_charge.get(r.id, []), "is_context": False, "is_extra": False}
        for r in charges
    ]
    for charge_id, charge in context_charges.items():
        kaarten.append(
            {
                "charge": charge,
                "refunds": per_charge.get(charge_id, []),
                "is_context": True,
                "is_extra": False,
            }
        )
    kaarten += [
        {"charge": r, "refunds": [], "is_context": False, "is_extra": False}
        for r in refunds
        if not r.refund_of_id
        or (r.refund_of_id not in charge_ids and r.refund_of_id not in context_charges)
    ]
    # Nieuwste eerst — dit bepaalt de volgorde TUSSEN de groepen: een groep komt in
    # de lijst te staan waar haar nieuwste kaart hem zet. Binnen een groep draaien
    # we het hieronder om (#682). Twee vragen, twee antwoorden; ze deelden één
    # sorteerregel en dat gaf de verkeerde uitkomst binnen een groep.
    kaarten.sort(key=lambda k: k["charge"].created_at, reverse=True)

    groepen: list[dict] = []
    volgorde: dict = {}
    for kaart in kaarten:
        charge = kaart["charge"]
        sleutel = (charge.payable_type, charge.payable_id)
        if sleutel not in volgorde:
            volgorde[sleutel] = len(groepen)
            groepen.append({"kaarten": [], "records": []})
        groep = groepen[volgorde[sleutel]]
        groep["kaarten"].append(kaart)
        # Een contextkaart telt niet mee: het totaal hoort bij wat het filter
        # selecteerde, niet bij wat we erbij tonen om het leesbaar te maken.
        if not kaart["is_context"]:
            groep["records"].append(charge)
        groep["records"].extend(kaart["refunds"])

    for groep in groepen:
        # #673: meerdere vorderingen op één inschrijving lazen als losse betalingen.
        # De oudste blijft de volledige kaart, de latere komen ingesprongen eronder.
        # Dat is VISUELE ordening, geen hiërarchie: tussen twee charges bestaat geen
        # verband zoals refund_of_id er een legt — het zijn broers op dezelfde
        # inschrijving. De template markeert dat verschil dan ook anders dan de
        # refund-nesting.
        echte = [
            k
            for k in groep["kaarten"]
            if not k["is_context"] and k["charge"].type != PaymentType.REFUND
        ]
        for kaart in sorted(echte, key=lambda k: k["charge"].created_at)[1:]:
            kaart["is_extra"] = True
        # #682: binnen een groep OUDSTE eerst. Hier vertelt de volgorde het verhaal
        # — de oorspronkelijke vordering, dan wat erop volgde — en nieuwste-eerst
        # zette de bijkomende vordering vóór de vordering waar ze bij hoort. Tussen
        # groepen blijft nieuwste eerst: dat is een lijstvraag, geen verhaalvraag.
        groep["kaarten"].sort(key=lambda k: k["charge"].created_at)
        groep["totaal"] = aggregate(groep["records"])
        groep["toon_totaal"] = len(groep["records"]) > 1
        groep["terug_te_betalen"] = _nog_uit_te_betalen(groep["records"])
    return groepen


def _nog_uit_te_betalen(records) -> Decimal:
    """Wat er van de terugbetalingen nog écht de deur uit moet (#682).

    GEEN tweede som van hetzelfde. `totaal.saldo` is bedrag min ontvangen over de
    hele groep; dit is een andere grootheid — het deel van de terugbetalingen dat
    nog niet uitbetaald is. De twee vallen vaak samen, maar niet altijd: een
    inschrijving die per ongeluk te veel betaald kreeg heeft ook een negatief saldo
    zonder dat er een terugbetaling openstaat.

    Waarom het apart moet staan: de totaalregel las "Bedrag 30,00 · Ontvangen 40,00
    · Saldo -10,00". Rekenkundig juist, maar "meer ontvangen dan gevorderd" leest
    als een fout, en het enige wat nog actie vraagt — die 10 euro uitbetalen — zat
    onzichtbaar in het saldo.

    Terugbetalingen dragen een negatief `amount` (interne conventie); hier rekenen
    we in absolute termen, want dit is wat de penningmeester uitbetaalt. Nooit
    negatief: een refund die méér uitbetaald kreeg dan gevorderd is een fout die
    elders thuishoort, niet een negatieve schuld in deze regel.
    """
    openstaand = Decimal("0")
    for r in records:
        if getattr(r, "type", None) != PaymentType.REFUND:
            continue
        rest = abs(_bedrag(r.amount)) - abs(_bedrag(r.amount_paid))
        if rest > 0:
            openstaand += rest
    return openstaand


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
        Activity,
        ActivitySubRegistration,
        Registration,
        RegistrationItem,
        compute_registration_total,
    )
    from app.domains.mdm.api import Member, MemberPerson
    from app.domains.membership.api import Membership
    from app.domains.payment.schemas import EnrichedPaymentRecord

    def _q(model):
        return db.query(model).execution_options(include_deleted=True)

    records = (
        db.query(PaymentRecord)
        .options(selectinload(PaymentRecord.gateway_payment))
        .order_by(PaymentRecord.created_at.desc())
        .all()
    )

    reg_ids = {r.payable_id for r in records if r.payable_type == PayableType.REGISTRATION}
    ms_ids = {r.payable_id for r in records if r.payable_type == PayableType.MEMBERSHIP}

    # Registraties mét items en producten in één keer: compute_registration_total
    # loopt over registration.items en elk item over zijn product.
    registraties = {}
    if reg_ids:
        registraties = {
            r.id: r
            for r in _q(Registration)
            .options(
                selectinload(Registration.items).selectinload(RegistrationItem.product),
                selectinload(Registration.person),
            )
            .filter(Registration.id.in_(reg_ids))
            .all()
        }
    activiteiten = {}
    onderdelen = {}
    if registraties:
        act_ids = {r.activity_id for r in registraties.values() if r.activity_id}
        comp_ids = {r.component_id for r in registraties.values() if r.component_id}
        if act_ids:
            activiteiten = {a.id: a for a in _q(Activity).filter(Activity.id.in_(act_ids)).all()}
        if comp_ids:
            onderdelen = {
                c.id: c
                for c in _q(ActivitySubRegistration)
                .filter(ActivitySubRegistration.id.in_(comp_ids))
                .all()
            }

    lidmaatschappen = {}
    hoofdlid_naam = {}
    if ms_ids:
        lidmaatschappen = {m.id: m for m in _q(Membership).filter(Membership.id.in_(ms_ids)).all()}
        member_ids = {m.member_id for m in lidmaatschappen.values()}
        if member_ids:
            leden = {m.id for m in _q(Member).filter(Member.id.in_(member_ids)).all()}
            koppels = (
                _q(MemberPerson)
                .filter(
                    MemberPerson.member_id.in_(leden),
                    MemberPerson.relation_type == RelationType.PRIMARY_MEMBER,
                )
                .all()
            )
            personen = {}
            if koppels:
                personen = {
                    p.id: p
                    for p in _q(Person).filter(Person.id.in_({k.person_id for k in koppels})).all()
                }
            for koppel in koppels:
                persoon = personen.get(koppel.person_id)
                if persoon is not None:
                    hoofdlid_naam[koppel.member_id] = f"{persoon.first_name} {persoon.last_name}"

    resultaat = []
    for r in records:
        contact_name = description = None
        activity_id = component_id = component_name = membership_year = None
        family_id = None
        reg_items: list = []

        if r.payable_type == PayableType.REGISTRATION:
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
                    reg_items = [
                        {
                            "product_name": regel["name"],
                            "quantity": regel["quantity"],
                            "unit_price": float(regel["unit_price"]),
                            "subtotal": float(regel["subtotal"]),
                        }
                        for regel in regels
                    ]
        elif r.payable_type == PayableType.MEMBERSHIP:
            # payable_id is de Membership.id (niet de Member.id) — het jaar komt
            # van het lidmaatschap, de naam van het hoofdlid van dat gezin (#141).
            ms = lidmaatschappen.get(r.payable_id)
            description = f"Lidmaatschap {ms.year}" if ms else "Lidmaatschap"
            membership_year = ms.year if ms else None
            if ms is not None:
                contact_name = hoofdlid_naam.get(ms.member_id)
                family_id = ms.member_id

        resultaat.append(
            EnrichedPaymentRecord(
                id=r.id,
                payable_type=r.payable_type,
                payable_id=r.payable_id,
                activity_id=activity_id,
                component_id=component_id,
                component_name=component_name,
                membership_year=membership_year,
                family_id=family_id,
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
            )
        )
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


#: The Dutch name the payment error had before CR-13 (§B4.4). The same class, not
#: a second one: `except BetalingFout` keeps catching `PaymentError`, which the
#: record itself raises since phase 2. Removed only when the last Dutch
#: reference is gone.
BetalingFout = PaymentError


def _ingetypt_bedrag(tekst: str | None) -> Decimal | None:
    """Een ingetypt bedrag, of None als er niets ingevuld is.

    Heet niet `_bedrag`: die naam is hierboven al in gebruik voor het lezen van een
    kolomwaarde. Komma én punt zijn toegestaan — op een Belgisch toetsenbord typ je
    een komma, en dat mag geen foutmelding opleveren.
    """
    if tekst is None or not tekst.strip():
        return None
    try:
        return Decimal(tekst.replace(",", "."))
    except (InvalidOperation, ArithmeticError):
        raise BetalingFout("Ongeldig bedrag.")


def _bestaand_record(db: Session, record_id: str):
    """Het record, of een LookupError met een leesbare melding (#723).

    De vier schermmutaties gaven bij een onbekend id ieder iets anders: `bewerk_betaling`
    een LookupError (→ 404), de andere drie een ValueError uit de laag eronder die als
    `BetalingFout` naar boven kwam. Sinds de reden van een `BetalingFout` op het scherm
    getoond wordt, is dat verschil zichtbaar geworden: "PaymentRecord <id> not found" is
    een interne zin, geen gebruikersmelding. Een verdwenen record is bovendien geen
    invoerfout — daar is "herlaad de pagina" het juiste antwoord, en dat is precies wat
    een 404 doet.
    """
    record = db.query(PaymentRecord).filter(PaymentRecord.id == record_id).first()
    if record is None:
        raise LookupError("Betaling niet gevonden.")
    return record


def bevestig_betaling(
    db: Session,
    record_id: str,
    *,
    note: str | None = None,
    amount_paid: str | None = None,
    actor: str | None = None,
):
    """ "Bevestig betaald", met optioneel het effectief ontvangen bedrag (#455).

    Vervroegt de sweep, net als `create_refund` (#855). Sinds #705 verschijnt een
    openstaande terugbetaling meteen op de werkbank; verdwijnen wachtte nog op de klok.
    Gemeten op HDEV, 10 september 2026: vereffend om 21:40, sweep net gelopen om 21:38,
    volgende om 22:38 — achtenvijftig minuten een taak in beeld voor werk dat al gedaan
    was.

    Dit dekt beide gevallen, want `/bevestigen` (vereffenen) en `/bijwerken` (een
    vordering afboeken, #617-2b) komen allebei hier langs.

    Since CR-13 phase 2 the sweep is advanced by `workflow`, subscribed to
    `PaymentReceived` — which every way money comes in publishes, this one included.
    That is what `PaymentSettled` could not do: only the Mollie path published it,
    so a listener missed exactly the manual confirmation. `PaymentSettled` is gone.

    **Vervroegen, niet zelf de taak sluiten.** Zelfde reden als #705: de titel is de
    idempotentiesleutel, en een tweede plek die daar iets mee doet is hoe dubbele of te
    vroeg gesloten taken ontstaan. De sweep beslist; dit zegt alleen "kijk nu".
    """
    _bestaand_record(db, record_id)
    try:
        record = confirm_manual_payment(
            db,
            record_id,
            (note or "").strip() or None,
            actor=actor,
            amount_paid=_ingetypt_bedrag(amount_paid),
        )
    except ValueError as exc:
        db.rollback()
        raise BetalingFout(str(exc)) from exc
    db.commit()
    return record


def registreer_terugbetaling(
    db: Session, record_id: str, *, amount: str, note: str | None = None, actor: str | None = None
):
    """ "Terugbetaling registreren" (#617-2b).

    `settled=False`: de terugbetaling ontstaat met een terug te betalen bedrag en
    een leeg uitbetaald bedrag, precies zoals een vordering ontstaat met een te
    betalen bedrag en niets ontvangen. Aanmaken en afboeken zijn twee stappen. De
    service-default blijft True voor andere aanroepers.
    """
    _bestaand_record(db, record_id)
    bedrag = _ingetypt_bedrag(amount)
    if bedrag is None:
        raise BetalingFout("Ongeldig bedrag.")
    try:
        refund = create_refund(
            db, record_id, bedrag, note=(note or "").strip() or None, actor=actor, settled=False
        )
    except ValueError as exc:
        db.rollback()
        raise BetalingFout(str(exc)) from exc
    db.commit()
    return refund


def bewerk_betaling(
    db: Session,
    record_id: str,
    *,
    status: str | None = None,
    amount_paid: str | None = None,
    note: str | None = None,
    actor: str | None = None,
):
    """Status, ontvangen bedrag en opmerking in één keer (#515).

    Het minteken op een terugbetaling is een boekhoudkundige interne conventie —
    zo kloppen de sommen — en dat hoort niemand in te typen. De penningmeester
    moest letterlijk "-40.00" invoeren, want "40.00" werd geweigerd (#617-2c). Het
    scherm toont mét teken, je voert in zonder, en hier draait het om. De grens
    (nooit meer dan het terug te betalen bedrag) hoort bij diezelfde regel.
    """
    from app.kernel.geld import bedrag as _geld

    record = db.query(PaymentRecord).filter(PaymentRecord.id == record_id).first()
    if record is None:
        raise LookupError("Betaling niet gevonden.")

    bedrag = _ingetypt_bedrag(amount_paid)
    if bedrag is not None and record.type == PaymentType.REFUND:
        grens = abs(Decimal(str(record.amount)))
        if abs(bedrag) > grens:
            raise BetalingFout(f"Meer dan het terug te betalen bedrag (€ {_geld(grens)}).")
        bedrag = -abs(bedrag)

    try:
        edit_payment_record(
            db,
            record_id,
            status=(status or "").strip() or None,
            amount_paid=bedrag,
            note=(note or "").strip() or None,
            actor=actor,
        )
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


def zet_betaalstatus(
    db: Session, record_id: str, status: str, *, note: str | None = None, actor: str | None = None
):
    """Vrije statuscorrectie door de penningmeester (#455)."""
    try:
        record = set_payment_status(
            db, record_id, (status or "").strip(), actor=actor, note=(note or "").strip() or None
        )
    except ValueError as exc:
        db.rollback()
        raise BetalingFout(str(exc)) from exc
    db.commit()
    return record


def verwijder_betaling(
    db: Session, record_id: str, *, note: str | None = None, actor: str | None = None
):
    """Soft-delete: uit het saldo, maar bewaard als financieel feit (#455).
    Corrigeert ook een foute terugbetaling."""
    _bestaand_record(db, record_id)
    try:
        record = void_payment_record(db, record_id, actor=actor, note=(note or "").strip() or None)
    except ValueError as exc:
        db.rollback()
        raise BetalingFout(str(exc)) from exc
    db.commit()
    return record


def checkout_url_for(db: Session, record) -> Optional[str]:
    """De betaal-URL van een record, of None.

    Een afgebroken online betaling kan hervat worden zolang de gateway haar
    checkout-URL nog kent (#618-3). Het gezinsportaal vroeg dat zelf op met een
    query op GatewayPayment; die koppeling hoort in het payment-domein.
    """
    if not getattr(record, "gateway_payment_id", None):
        return None
    from app.domains.payment.models import GatewayPayment

    gateway = (
        db.query(GatewayPayment).filter(GatewayPayment.id == record.gateway_payment_id).first()
    )
    return getattr(gateway, "checkout_url", None)
