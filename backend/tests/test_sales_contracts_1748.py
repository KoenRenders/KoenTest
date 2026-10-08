"""The webshop's two event contracts stand before either side is built (CR-21 phase 0, #1748).

`payment` and `mail` will subscribe to them and `sales` will publish them, each built by
another session on another branch. What they agree on is this file's subject: the names
and the fields. A field renamed here breaks a subscriber that is not on `master` yet, so
the shape is pinned.

Proven by violation: `actor` renamed to `audit_actor` in `SalesOrderChanged` turns the
test red on its fields. That the contracts are frozen needs no test: `KernelEvent` is
frozen and Python refuses a subclass that is not ("cannot inherit non-frozen dataclass
from a frozen one" — tried).
"""

from __future__ import annotations

import dataclasses

from app.kernel.contracts.sales import SalesOrderChanged, SalesOrderPlaced
from app.kernel.events import KernelEvent


def _fields(event) -> list[str]:
    return [field.name for field in dataclasses.fields(event)]


def test_the_two_contracts_carry_the_fields_the_design_names():
    assert _fields(SalesOrderPlaced) == ["order_id", "payment_record_id"]
    assert _fields(SalesOrderChanged) == ["order_id", "total_due", "actor"]
    assert issubclass(SalesOrderPlaced, KernelEvent) and issubclass(SalesOrderChanged, KernelEvent)
    # Events are plain data: a total as a string, and an actor nobody has to give.
    changed = SalesOrderChanged(order_id=1, total_due="12.50")
    assert dataclasses.asdict(changed) == {"order_id": 1, "total_due": "12.50", "actor": None}
