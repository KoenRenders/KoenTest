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
