"""What the payment component does when another component says something happened.

Events, not calls (CR-13 §B4.9): a component that changes something payment must
follow publishes an event; payment subscribes here. Handlers run synchronously, in
the publisher's transaction, and never commit — the door service does, once (§B4.1).
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy.orm import Session

from app.domains.payment.models import PayableType
from app.domains.payment.service import reconcile_charges
from app.kernel.contracts.activities import OrderChanged
from app.kernel.contracts.membership import MembershipDeleted
from app.kernel.events import subscribe


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
