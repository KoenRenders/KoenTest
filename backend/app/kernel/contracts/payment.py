"""Events die het payment-component publiceert (contract, zie payment/CONTRACT.md)."""
from __future__ import annotations

from dataclasses import dataclass

from app.kernel.events import KernelEvent


@dataclass(frozen=True)
class PaymentSettled(KernelEvent):
    """Een betaling is bevestigd (status 'paid'), synchroon in-transactie
    gepubliceerd vanuit de (idempotente) gateway-update — een herhaalde webhook
    publiceert dus niet opnieuw."""

    payment_record_id: str
    payable_type: str
    payable_id: int
    amount: str  # Decimal als string — events zijn platte data
    method: str
