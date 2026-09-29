"""A registration's lines come back in the order they were added (#1352).

`Registration.items` had no order, so the lines followed the order PostgreSQL
returned them in: a characterisation snapshot of the back office's registration
list read "1× Product on_site, 2× Product paid, 1× Product free" once in a large
run, where it had recorded the lines in the order they were added. The detail
pairs the lines with the amounts of `compute_registration_total` by position; both
read this one collection, so an order on it holds for both.

The CLAUSE is tested, as for #1340: which order PostgreSQL returns without one
depends on the plan and the table's history, and the snapshot showed that only in
a large run — a behaviour test here would be green on the broken code too.

Broken on purpose to check this test can go red (run, then restored): `order_by`
removed from `Registration.items` → the test fails on an empty order.
"""

import pytest

from app.domains.activities.api import Registration

pytestmark = pytest.mark.ui_agnostisch


def test_the_lines_are_ordered_by_id():
    keys = [getattr(k, "name", str(k)) for k in Registration.items.property.order_by or []]
    assert keys == ["id"], keys
