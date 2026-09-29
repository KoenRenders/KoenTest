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
