"""The membership card: how a household's membership stands (CR-22 S2, #1705;
R26).

One view-model and one partial (`_membership_card.html`) for every place that
shows it — Mijn gezin today, the landing page after signing in from CR-22 S3 on.
Until #1705 its fields stood on the household page's own view-model and its
markup in that page.

Three states in one place (#1632, CR-11 Q73): valid until a date, a renewal
that runs — with the transfer to make or the online payment to resume, at most
one of the two (#618, #1641) — or renewing is possible.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.domains.mdm.api import PaymentMethod
from app.domains.payment.api import TransferDue


@dataclass(frozen=True)
class OnlineDue:
    amount: Any
    checkout_url: Optional[str]


@dataclass(frozen=True)
class MembershipCard:
    valid_until: Optional[date]
    renewal_available: bool
    board_member_name: Optional[str]
    #: A renewal that runs stands in the card itself, and only there (#1632,
    #: #1641): the transfer to make, or the online payment to resume.
    transfer: Optional[TransferDue] = None
    online: Optional[OnlineDue] = None

    @property
    def renewal_running(self) -> bool:
        return bool(self.transfer or self.online)


def _running_renewal(db: Session, person) -> tuple[Optional[TransferDue], Optional[OnlineDue]]:
    """How an open renewal stands (#618): `(transfer, online)`, at most one set."""
    from app.domains.membership.api import household_member_for, open_renewal_payment
    from app.domains.payment.api import checkout_url_for, transfer_due
    from app.i18n import _

    try:
        member = household_member_for(db, person)
    except Exception:
        return None, None
    record = open_renewal_payment(db, member) if member is not None else None
    if record is None:
        return None, None
    if record.method == PaymentMethod.TRANSFER:
        heading = _("Vernieuwing geregistreerd — betaal via overschrijving:")
        return transfer_due(db, record, heading), None
    # Broken off at the provider (#618-3): with a checkout URL the member can
    # resume; without one only the explanation that it is still running.
    return None, OnlineDue(amount=record.amount, checkout_url=checkout_url_for(db, record))


def renewal_is_running(db: Session, person) -> bool:
    """Does a renewal of this person's household wait for its payment?"""
    return any(_running_renewal(db, person))


def membership_card(db: Session, person, *, household: Optional[dict] = None) -> MembershipCard:
    """The card of the household `person` belongs to. `household` is the
    household view when the caller has it already (Mijn gezin); otherwise it is
    read here."""
    from app.domains.membership.api import (
        household_view,
        membership_coverage_until,
        renewal_available,
    )

    if household is None:
        household = household_view(db, person)
    # Cover up to and including an already paid next year (#496).
    valid_until = membership_coverage_until(person)
    transfer, online = _running_renewal(db, person)
    return MembershipCard(
        valid_until=valid_until,
        renewal_available=renewal_available(valid_until, date.today()),
        board_member_name=household.get("board_member_name"),
        transfer=transfer,
        online=online,
    )
