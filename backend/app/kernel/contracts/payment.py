"""Events the payment component publishes (contract, see payment/CONTRACT.md), and
the port it handles for starting a payment."""

from __future__ import annotations

from dataclasses import dataclass

from app.kernel.events import KernelEvent
from app.kernel.ports import Port


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


@dataclass(frozen=True)
class PaymentStarted:
    """The outcome of `CreatePayment`: the record, and for an online payment the
    checkout url the caller redirects to."""

    payment_record_id: str
    checkout_url: str = ""


@dataclass(frozen=True)
class CreatePayment(Port):
    """Start a payment for an order, as a registration starts one (CR-21 Q64).

    Handled by payment. `amount` is a Decimal as a string — ports are plain data.
    For an online payment the provider is called here, in the caller's
    transaction. The handler lets through, by name, the payment seam's refusal:
    `ValueError` (a missing key, a refusal or an error answer of the provider) and
    `httpx.HTTPError` (the provider could not be reached, a timeout); the caller's
    door rolls the whole order back on those. Nothing is committed here.
    """

    payable_type: str
    payable_id: int
    amount: str
    method: str
    redirect_url: str = ""
    description: str = ""
    audit_source: str = "system"
    audit_actor: str | None = None
