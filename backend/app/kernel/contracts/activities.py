"""Events the activities component publishes (contract, see activities/CONTRACT.md)."""

from __future__ import annotations

from dataclasses import dataclass

from app.kernel.events import KernelEvent


@dataclass(frozen=True)
class OrderChanged(KernelEvent):
    """A registration's order lines changed — added, changed, removed, or all of them
    gone with the registration (CR-13 phase 1, §B4.9).

    Published by the activities service after the change, in the same transaction;
    `payment` subscribes and brings the registration's charges to `total_due` — the
    #185 rule, which lived as a direct call into `payment.api` until phase 1. A
    subscriber that raises rolls the order change back: the lines never stay changed
    with a balance that did not follow.

    `total_due` is the registration's total as its owner computes it (`activities`),
    a Decimal as a string — events are plain data. `actor` signs the audit rows the
    reconciliation writes, as the direct call did.
    """

    registration_id: int
    total_due: str
    actor: str | None = None


@dataclass(frozen=True)
class RegistrationConfirmed(KernelEvent):
    """A registration for an activity is saved and its payment started (CR-13 phase 4).

    Published by the registration door right before its commit; `mail` subscribes and
    queues the confirmation mail as a job in the same transaction — so a rolled-back
    registration sends nothing, and a sent mail always has a registration behind it.
    Until phase 4 the door called `mail.api` after the commit.

    `to_email` and `name` are what the form carried (#1284: the confirmation goes to
    the address typed in, not the member's main address).
    """

    registration_id: int
    to_email: str
    name: str
    payment_record_id: str | None = None


@dataclass(frozen=True)
class AnswerLinkSent(KernelEvent):
    """The board sends a registration its answer link, or sends it again (CR-14
    phase 3, §B4.8): "link sturen" for a registration that had none, "link opnieuw
    sturen" for one whose link is still open.

    Published by the activities service in the transaction that made or kept the
    token; `mail` subscribes and queues the reminder — the confirmation with the
    subject "Herinnering: de vragen voor <activity>" and the link.
    """

    registration_id: int
    to_email: str
    name: str


@dataclass(frozen=True)
class ActivityCopied(KernelEvent):
    """An activity was copied to a next year (#1397).

    Published by `copy_activity` inside the copy's transaction, after the new
    activity and its dates are flushed. `designstudio` subscribes and gives the
    copy its own design from the source's (Koen, 30 September 2026): a subscriber
    that raises undoes the whole copy.
    """

    source_activity_id: int
    copy_activity_id: int
    actor: str | None = None
