"""Events the membership component publishes (contract, see membership/CONTRACT.md)."""

from __future__ import annotations

from dataclasses import dataclass, field

from app.kernel.events import KernelEvent


@dataclass(frozen=True)
class FamilyRegistered(KernelEvent):
    """A household registered itself through the public form (CR-13 phase 4).

    Published by the registration door right before its commit; `mail` subscribes and
    queues the welcome mail as a job in the same transaction. Until phase 4 the door
    called `mail.api` after the commit.

    `form` is what the visitor submitted, as plain data: the mail repeats it, and the
    mail says what was sent — not what the database made of it. It lives in memory
    for the length of the request; the mail job keeps only the finished message, and
    only until it is sent.
    """

    member_id: int
    to_email: str
    name: str
    municipality: str = ""
    payment_record_id: str | None = None
    form: dict = field(default_factory=dict)


@dataclass(frozen=True)
class MembershipDeleted(KernelEvent):
    """A membership was deleted by the board — on its own, or with its household
    (CR-13 phase 4c, #1251).

    Published by membership right after the membership is soft-deleted, in the
    transaction of the deletion. `payment` subscribes and lets the money follow
    (#619): an open charge of the membership goes, a paid amount stays as a fact
    and gets one pending refund for the treasurer to confirm. Until phase 4c
    membership called `payment.api.reconcile_charges` for it.

    The consequence is not optional: the publisher refuses to publish when
    nothing subscribes.
    """

    membership_id: int
    #: The board member who deleted it, for payment's history rows.
    actor: str | None = None
