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
