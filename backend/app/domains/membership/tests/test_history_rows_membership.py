"""The history rows of membership, recorded (CR-13 phase 4c, cut C5, #1251).

The snapshot functions of membership move from `audit/service.py` to their owner
(`docs/architecture.md` §5.8: a history table per component, written by its
owner). The move changes no row: each function is given one fixed source and
every column of the row it writes is compared with what the code wrote before
the move. `EXPECTED` was recorded on the old code (9 October 2026, the functions
still in `audit/service.py`) and has not been touched since: the move changed the import
above and nothing below it.

Proven red (9 October 2026): `valid_to=membership.valid_to` taken out of `snapshot_membership` → its row differs.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.domains.membership.api import MembershipHistory
from app.domains.membership.history import snapshot_membership
from tests._snapshot import recorded_history_rows

pytestmark = pytest.mark.ui_agnostisch

EXPECTED: list[tuple[str, dict]] = [
    (
        "snapshot_membership",
        {
            "membership_id": 884001,
            "member_id": 883002,
            "year": 2026,
            "is_active": True,
            "valid_from": "2026-01-01",
            "valid_to": "2026-12-31",
            "operation": "update",
            "action": "recorded_0",
            "source": "recording",
            "actor": "board@example.org",
        },
    )
]


def test_every_snapshot_of_membership_writes_the_row_it_wrote(db_session):
    rows = recorded_history_rows(
        db_session,
        [
            (
                snapshot_membership,
                MembershipHistory,
                SimpleNamespace(
                    id=884_001,
                    member_id=883_002,
                    year=2026,
                    is_active=True,
                    valid_from=date(2026, 1, 1),
                    valid_to=date(2026, 12, 31),
                ),
            ),
        ],
    )
    assert rows == EXPECTED
