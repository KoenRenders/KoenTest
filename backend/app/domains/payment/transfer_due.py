"""What someone still has to pay by bank transfer, said once (CR-22 S2, #1705;
R27; one wording since #1775).

One view-model for every place that says how to transfer — the screens (a
renewal that runs in the membership card, a registration still to be paid) and
the two confirmation mails. Until #1705 the renewal carried its own copy; until
#1775 the mails had their own wording and their own reading of the settings:
"Rekeningnummer" where the screen said "IBAN", "Mededeling (OGM)" where the mail
said "Gestructureerde mededeling", and a date only in the mail.

`TransferDue.lines` is the one source: the five lines with their label and their
value, in the words Koen fixed on 8 October 2026 — Bedrag, IBAN, Begunstigde,
Gestructureerde mededeling, Te betalen vóór. The screen's partial
(`_transfer_due.html`) and the mail block both render those lines and add
nothing of their own.

Amount and reference come **from the booking itself**, not again from a price
rule: if the price changes between two visits the screen would show another
amount than what is due. The account and its holder are the tenant's. The date
is the day the booking was made plus the tenant's payment term, so the mail and
the screen name the same day whenever they are read.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.domains.mdm.api import PaymentMethod


@dataclass(frozen=True)
class TransferLine:
    label: str
    value: str
    #: What the payer copies into the banking app: shown with emphasis.
    to_copy: bool = False


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
    pay_before: Optional[date] = None

    @property
    def lines(self) -> list[TransferLine]:
        """The lines of the transfer, in order; one without a value is left out."""
        from app.i18n import _
        from app.kernel.geld import bedrag

        candidates = [
            TransferLine(_("Bedrag"), f"€ {bedrag(self.amount)}", to_copy=True),
            TransferLine(_("IBAN"), self.iban or "", to_copy=True),
            TransferLine(_("Begunstigde"), self.beneficiary or ""),
            TransferLine(_("Gestructureerde mededeling"), self.ogm or "", to_copy=True),
            TransferLine(
                _("Te betalen vóór"),
                self.pay_before.strftime("%d/%m/%Y") if self.pay_before else "",
            ),
        ]
        return [line for line in candidates if line.value]


def transfer_due(db: Session, record, heading: str) -> Optional[TransferDue]:
    """The transfer a booking (`PaymentRecord`) still asks for; None for a
    booking that is not paid by transfer, or for none at all."""
    from app.kernel.clock import BELGIUM, belgian_today
    from app.kernel.tenant_config import (
        tenant_payment_beneficiary,
        tenant_payment_iban,
        tenant_payment_term_days,
    )

    if record is None or record.method is not PaymentMethod.TRANSFER:
        return None
    made = record.created_at.astimezone(BELGIUM).date() if record.created_at else belgian_today()
    return TransferDue(
        heading=heading,
        amount=record.amount,
        ogm=record.structured_communication,
        iban=tenant_payment_iban(db),
        beneficiary=tenant_payment_beneficiary(db),
        pay_before=made + timedelta(days=tenant_payment_term_days(db)),
    )
