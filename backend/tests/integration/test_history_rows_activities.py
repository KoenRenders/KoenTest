"""The history rows of activities, recorded (CR-13 phase 4c, cut C5, #1251).

The snapshot functions of activities move from `audit/service.py` to their owner
(`docs/architecture.md` §5.8: a history table per component, written by its
owner). The move changes no row: each function is given one fixed source and
every column of the row it writes is compared with what the code wrote before
the move. `EXPECTED` was recorded on the old code (9 October 2026, the functions
still in `audit/service.py`) and has not been touched since.

Proven red (9 October 2026): `name=product.name` taken out of `snapshot_product` → its row differs.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from app.domains.activities.api import (
    ActivityDateHistory,
    ActivityHistory,
    ComponentHistory,
    ProductHistory,
    RegistrationItemHistory,
)
from app.domains.audit.api import (
    snapshot_activity,
    snapshot_activity_date,
    snapshot_component,
    snapshot_product,
    snapshot_registration_item,
)
from tests._snapshot import recorded_history_rows

pytestmark = pytest.mark.ui_agnostisch

EXPECTED: list[tuple[str, dict]] = [
    (
        "snapshot_activity",
        {
            "activity_id": 882001,
            "name": "Quiz night",
            "operation": "update",
            "action": "recorded_0",
            "source": "recording",
            "actor": "board@example.org",
        },
    ),
    (
        "snapshot_activity_date",
        {
            "activity_date_id": 882002,
            "activity_id": 882001,
            "start_date": "2026-11-14",
            "end_date": "2026-11-15",
            "operation": "update",
            "action": "recorded_1",
            "source": "recording",
            "actor": "board@example.org",
        },
    ),
    (
        "snapshot_component",
        {
            "component_id": 882003,
            "activity_id": 882001,
            "name": "Evening part",
            "price": "12.50",
            "member_price": "10.00",
            "operation": "update",
            "action": "recorded_2",
            "source": "recording",
            "actor": "board@example.org",
        },
    ),
    (
        "snapshot_product",
        {
            "product_id": 882004,
            "component_id": 882003,
            "name": "Adult",
            "price": "8.00",
            "member_price": None,
            "operation": "update",
            "action": "recorded_3",
            "source": "recording",
            "actor": "board@example.org",
        },
    ),
    (
        "snapshot_registration_item",
        {
            "registration_item_id": 882005,
            "registration_id": 882006,
            "product_id": 882004,
            "quantity": 3,
            "operation": "update",
            "action": "recorded_4",
            "source": "recording",
            "actor": "board@example.org",
        },
    ),
]


def test_every_snapshot_of_activities_writes_the_row_it_wrote(db_session):
    rows = recorded_history_rows(
        db_session,
        [
            (snapshot_activity, ActivityHistory, SimpleNamespace(id=882_001, name="Quiz night")),
            (
                snapshot_activity_date,
                ActivityDateHistory,
                SimpleNamespace(
                    id=882_002,
                    activity_id=882_001,
                    start_date=date(2026, 11, 14),
                    end_date=date(2026, 11, 15),
                ),
            ),
            (
                snapshot_component,
                ComponentHistory,
                SimpleNamespace(
                    id=882_003,
                    activity_id=882_001,
                    name="Evening part",
                    price=Decimal("12.50"),
                    member_price=Decimal("10.00"),
                ),
            ),
            (
                snapshot_product,
                ProductHistory,
                SimpleNamespace(
                    id=882_004,
                    component_id=882_003,
                    name="Adult",
                    price=Decimal("8.00"),
                    member_price=None,
                ),
            ),
            (
                snapshot_registration_item,
                RegistrationItemHistory,
                SimpleNamespace(
                    id=882_005, registration_id=882_006, product_id=882_004, quantity=3
                ),
            ),
        ],
    )
    assert rows == EXPECTED
