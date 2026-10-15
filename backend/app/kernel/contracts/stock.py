"""The ports stock handles (contract, see stock/CONTRACT.md) — `kernel/ports.py`,
`docs/architecture.md` §3.2.1 step 2.

`sales` reserves an order's lines through here (CR-21 Q64): a synchronous command
whose outcome the caller needs — the reservation, or the refusal that rolls the
whole order back.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.kernel.ports import Port


@dataclass(frozen=True)
class ReservationMade:
    """The outcome of `ReserveStock`: the order line whose reservation was written."""

    order_line_id: int


@dataclass(frozen=True)
class ReserveStock(Port):
    """Reserve a quantity of a variant for one order line (F1, R13, C4.1).

    Handled by stock. `allow_short` lets an article "Op bestelling" reserve beyond
    what is on hand (R39). Refused with stock's `NotEnoughStock` when the available
    quantity does not cover the reservation and `allow_short` is off. Nothing is
    committed here; the caller's door commits once.
    """

    order_line_id: int
    variant_id: int
    quantity: int
    allow_short: bool = False


@dataclass(frozen=True)
class ReleaseStock(Port):
    """Cancel the reservation of an order line (F8): the article is free again.
    Nothing happens when the line has no open reservation."""

    order_line_id: int


@dataclass(frozen=True)
class StockReleased:
    """The outcome of `ReleaseStock`: the reservation was cancelled."""

    order_line_id: int


@dataclass(frozen=True)
class IssueStock(Port):
    """Deliver an order line (F6, R21): a GOODS_ISSUE movement of its quantity and
    the reservation DELIVERED. Refused with `NotEnoughStock` while the on hand does
    not cover the line."""

    order_line_id: int
    actor: str | None = None


@dataclass(frozen=True)
class StockIssued:
    """The outcome of `IssueStock`: the line was delivered."""

    order_line_id: int
