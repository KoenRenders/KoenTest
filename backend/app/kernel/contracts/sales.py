"""Events the sales component publishes (contract, CR-21 — the webshop).

The component itself comes with CR-21 phase 2; the contract stands here from phase 0
(#1748) so that what `payment` and `mail` will subscribe to has one name and one shape
before either side is built. Until then nothing publishes these and nothing subscribes.

The names carry `Sales` because `OrderChanged` (`contracts/activities.py`) already means
a registration's order lines.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.kernel.events import KernelEvent


@dataclass(frozen=True)
class SalesOrderPlaced(KernelEvent):
    """A webshop order is saved and its payment started.

    Published by the order's door inside its transaction, as `RegistrationConfirmed`
    is for a registration: a subscriber that queues the confirmation mail does so in
    the same transaction, so a rolled-back order sends nothing.

    `payment_record_id` is the charge the order opened — a string, as in the payment
    contract.
    """

    order_id: int
    payment_record_id: str


@dataclass(frozen=True)
class SalesOrderChanged(KernelEvent):
    """A webshop order's lines changed — or all of them are gone with the order.

    The counterpart of `OrderChanged` for a registration: `payment` brings the order's
    charges to `total_due`. A cancelled order is a change to a total of 0 (CR-21 Q61),
    so there is no separate cancel event.

    `total_due` is the order's total as its owner computes it, a Decimal as a string —
    events are plain data. `actor` signs the audit rows the reconciliation writes.
    """

    order_id: int
    total_due: str
    actor: str | None = None
