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
    #: The household never had a paid membership (#1730; Koen, 8 October 2026):
    #: it pays a membership, it does not renew one. Since #1737 this decides
    #: the card's button only; every other sentence is one for everyone.
    first_membership: bool = False

    @property
    def pay_label(self) -> str:
        """The word on the way to the payment."""
        from app.i18n import _

        return _("Lidmaatschap betalen") if self.first_membership else _("Lidmaatschap vernieuwen")

    @property
    def renewal_running(self) -> bool:
        return bool(self.transfer or self.online)


def _household(db: Session, person):
    from app.domains.membership.api import household_member_for

    try:
        return household_member_for(db, person)
    except Exception:
        return None


def _running_renewal(db: Session, person) -> tuple[Optional[TransferDue], Optional[OnlineDue]]:
    """How an open membership payment stands (#618): `(transfer, online)`, at
    most one set. The transfer block reads the same for a household that
    never paid and for one that renews (#1737): "Lidmaatschap geregistreerd"."""
    from app.domains.membership.api import open_renewal_payment
    from app.domains.payment.api import checkout_url_for, transfer_due
    from app.i18n import _

    member = _household(db, person)
    record = open_renewal_payment(db, member) if member is not None else None
    if record is None:
        return None, None
    due = transfer_due(db, record, _("Lidmaatschap geregistreerd — betaal via overschrijving:"))
    if due is not None:
        return due, None
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
        is_first_membership,
        membership_coverage_until,
        renewal_available,
    )

    if household is None:
        household = household_view(db, person)
    # Cover up to and including an already paid next year (#496).
    valid_until = membership_coverage_until(person)
    member = _household(db, person)
    first = member is not None and is_first_membership(db, member)
    transfer, online = _running_renewal(db, person)
    return MembershipCard(
        valid_until=valid_until,
        renewal_available=renewal_available(valid_until, date.today()),
        board_member_name=household.get("board_member_name"),
        transfer=transfer,
        online=online,
        first_membership=first,
    )
