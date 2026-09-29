"""Events the payment component publishes (contract, see payment/CONTRACT.md)."""

from __future__ import annotations

from dataclasses import dataclass

from app.kernel.events import KernelEvent


@dataclass(frozen=True)
class PaymentReceived(KernelEvent):
    """Money was booked on a payment record — in full or in part (CR-13 phase 2).

    Returned by `PaymentRecord.mark_paid` and published by the payment service on
    every way money comes in: the provider's webhook, "bevestig betaald" and the
    treasurer's status correction. It replaced `PaymentSettled`, which only the
    webhook published and nothing subscribed to — one event for one fact.

    `fully_paid` is whether the booked amount covers the record (#720): a partial
    payment is received money, but it does not, for instance, activate a
    membership. Amounts are Decimals as strings — events are plain data. `source`
    and `actor` sign the history rows a subscriber writes, as the direct call did.
    """

    payment_record_id: str
    payable_type: str
    payable_id: int
    amount_booked: str
    fully_paid: bool
    method: str
    source: str = "system"
    actor: str | None = None


@dataclass(frozen=True)
class RefundDue(KernelEvent):
    """A refund was created and has yet to be paid out (CR-13 phase 2, #705).

    Published by `create_refund`. `amount` is the refund's (negative) amount as a
    string.
    """

    refund_record_id: str
    payable_type: str
    payable_id: int
    amount: str
