"""What the payment component does when another component says something happened.

Events, not calls (CR-13 §B4.9): a component that changes something payment must
follow publishes an event; payment subscribes here. Handlers run synchronously, in
the publisher's transaction, and never commit — the door service does, once (§B4.1).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.domains.payment.models import PayableType
from app.domains.payment.service import create_payment_record, reconcile_charges
from app.kernel.contracts.activities import OrderChanged
from app.kernel.contracts.membership import MembershipDeleted
from app.kernel.contracts.payment import CreatePayment, PaymentStarted
from app.kernel.contracts.sales import SalesOrderChanged
from app.kernel.events import subscribe
from app.kernel.ports import handles


@subscribe(OrderChanged)
def reconcile_registration_on_order_change(event: OrderChanged, db: Session) -> None:
    """The charges follow the order (#185): bring them to the total activities
    computed. The same `reconcile_charges` the direct call ran, unchanged."""
    reconcile_charges(
        db,
        PayableType.REGISTRATION,
        event.registration_id,
        Decimal(event.total_due),
        audit_actor=event.actor,
    )


@subscribe(MembershipDeleted)
def reconcile_charges_of_deleted_membership(event: MembershipDeleted, db: Session) -> None:
    """The money follows a deleted membership (#619). Nobody owes anything for it
    any more — `total_due = 0` — so its open charges go; a paid amount stays as a
    financial fact and yields one `pending` refund, which the treasurer confirms
    (as in #617). Without this an unpaid charge stayed on the payments list for a
    membership that no longer exists, and a paid one raised no refund at all: the
    orphan job does not notice, because it treats a soft-deleted payable as
    existing on purpose.

    The same `reconcile_charges` membership called directly until CR-13 phase 4c,
    with the same arguments."""
    reconcile_charges(
        db,
        PayableType.MEMBERSHIP,
        event.membership_id,
        Decimal(0),
        audit_actor=event.actor,
        source="membership-delete",
        refund_note="Automatisch bij schrappen lidmaatschap — terugstorting te bevestigen",
    )


@subscribe(SalesOrderChanged)
def reconcile_order_on_change(event: SalesOrderChanged, db: Session) -> None:
    """The money follows a changed order (D4, R16): bring its charges to the total
    `sales` computed. A cancelled order is a change to a total of 0 (Q61)."""
    reconcile_charges(
        db,
        PayableType.ORDER,
        event.order_id,
        Decimal(event.total_due),
        audit_actor=event.actor,
        source="sales-order-edit",
    )


@handles(CreatePayment)
def start_payment(port: CreatePayment, db: Session) -> PaymentStarted:
    """Start a payment for an order (the port's handler, CR-21 Q64). For an online
    payment the provider is called here; its refusal passes through untouched."""
    from app.domains.mdm.api import PaymentMethod

    record = create_payment_record(
        db=db,
        payable_type=port.payable_type,
        payable_id=port.payable_id,
        amount=Decimal(port.amount),
        method=PaymentMethod(port.method),
        redirect_url=port.redirect_url,
        description=port.description,
        audit_source=port.audit_source,
        audit_actor=port.audit_actor,
    )
    checkout_url = ""
    if PaymentMethod(port.method) == PaymentMethod.ONLINE and record.gateway_payment_id:
        from app.domains.payment.api import GatewayPayment

        gateway = (
            db.query(GatewayPayment).filter(GatewayPayment.id == record.gateway_payment_id).first()
        )
        checkout_url = gateway.checkout_url if gateway is not None else ""
    return PaymentStarted(payment_record_id=str(record.id), checkout_url=checkout_url)
