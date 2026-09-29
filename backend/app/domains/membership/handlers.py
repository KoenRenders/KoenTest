"""What the membership component does when another component says something happened.

Events, not calls (CR-13 §B4.9). Handlers run synchronously in the publisher's
transaction and never commit or reach the network.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.domains.membership.service import activate_after_payment
from app.kernel.contracts.payment import PaymentReceived
from app.kernel.events import subscribe


@subscribe(PaymentReceived)
def activate_membership_on_payment(event: PaymentReceived, db: Session) -> None:
    """A membership is activated once its payment covers it (#113, #143, #720).

    Until CR-13 phase 2 `payment` did this itself, writing `membership`'s rows; the
    contract's one declared exception is now the ordinary pattern. A partial payment
    does not activate: the rest is still owed.
    """
    from app.domains.payment.api import PayableType

    if PayableType(event.payable_type) is not PayableType.MEMBERSHIP or not event.fully_paid:
        return
    activate_after_payment(db, event.payable_id, source=event.source, actor=event.actor)
