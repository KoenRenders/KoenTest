"""A stand-in payment provider for the e2e tests of the online chain (#1274).

It plays Mollie's part without money: `create_payment` hands out a checkout
URL on our own pretend checkout page, and `get_payment_details` reports what
that page recorded. It exists only where `settings.payment_stub_allowed` is
true — development and the tests — and `gateway_service._get_provider` refuses
it everywhere else.

**The stub keeps its own state, and it starts at `open`.** That is the whole
point of it. A stub that always answered *paid* would let a test pass even if
the webhook believed its own request body, and then the chain would be tested
without the rule under it (`CLAUDE.md`: the webhook always re-fetches status
and amount). Here the payment is *paid* only after the pretend checkout page
recorded a payment, so a webhook that arrives before that must still see *open*.

The state lives in this process. That is enough for what it is for: the test
server runs one worker, and `pytest` runs in one process.
"""
from __future__ import annotations

import secrets
from dataclasses import dataclass
from decimal import Decimal

from app.domains.payment.models import PaymentStatus

from .base import BaseProvider, PaymentResult, PaymentStatusResult


@dataclass
class StubPayment:
    amount: Decimal
    redirect_url: str
    webhook_url: str
    status: PaymentStatus = PaymentStatus.PENDING


#: provider_payment_id → what the pretend provider knows about it.
PAYMENTS: dict[str, StubPayment] = {}

#: Where the pretend checkout page lives (`payment/stub_router.py`).
CHECKOUT_PATH = "/betaling/stub"


def pay(provider_payment_id: str) -> StubPayment:
    """What the pretend checkout page does when its one button is pressed."""
    payment = PAYMENTS[provider_payment_id]
    payment.status = PaymentStatus.PAID
    return payment


class StubProvider(BaseProvider):
    def __init__(self, api_key: str | None = None):
        # A real provider needs the tenant's key; the stub has no account.
        self._api_key = api_key

    def create_payment(self, amount: Decimal, description: str, redirect_url: str,
                       webhook_url: str, metadata: dict) -> PaymentResult:
        payment_id = f"stub_{secrets.token_hex(8)}"
        PAYMENTS[payment_id] = StubPayment(amount=Decimal(str(amount)),
                                           redirect_url=redirect_url,
                                           webhook_url=webhook_url)
        return PaymentResult(provider_payment_id=payment_id,
                             checkout_url=f"{CHECKOUT_PATH}/{payment_id}",
                             status=PaymentStatus.PENDING.value)

    def get_payment_details(self, provider_payment_id: str) -> PaymentStatusResult:
        payment = PAYMENTS[provider_payment_id]
        return PaymentStatusResult(status=payment.status.value, amount=payment.amount,
                                   currency="EUR")
