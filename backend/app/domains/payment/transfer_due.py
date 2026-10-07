"""What someone still has to pay by bank transfer, as a screen shows it (CR-22
S2, #1705; R27).

One view-model and one partial (`_transfer_due.html`, in the shared templates of
`app/ui`) for every place that says how to transfer: a renewal that runs in the
membership card, and — from CR-22 on — a registration still to be paid. Until
#1705 the renewal carried its own copy of both.

Amount and reference come **from the booking itself**, not again from a price
rule: if the price changes between two visits the screen would show another
amount than what is due. The account and its holder are the tenant's.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from sqlalchemy.orm import Session


@dataclass(frozen=True)
class TransferDue:
    #: What the block says above the lines; the caller's words ("Vernieuwing
    #: geregistreerd — betaal via overschrijving:").
    heading: str
    amount: Any
    #: The structured communication (OGM) of the booking.
    ogm: Optional[str]
    iban: Optional[str]
    beneficiary: Optional[str]


def transfer_due(db: Session, record, heading: str) -> TransferDue:
    """The transfer a booking (`PaymentRecord`) still asks for."""
    from app.kernel.tenant_config import tenant_payment_beneficiary, tenant_payment_iban

    return TransferDue(
        heading=heading,
        amount=record.amount,
        ogm=record.structured_communication,
        iban=tenant_payment_iban(db),
        beneficiary=tenant_payment_beneficiary(db),
    )
