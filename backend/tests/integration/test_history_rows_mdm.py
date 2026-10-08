"""The history rows of mdm, recorded (CR-13 phase 4c, cut C5, #1251).

The snapshot functions of mdm move from `audit/service.py` to their owner
(`docs/architecture.md` §5.8: a history table per component, written by its
owner). The move changes no row: each function is given one fixed source and
every column of the row it writes is compared with what the code wrote before
the move. `EXPECTED` was recorded on the old code (9 October 2026, the functions
still in `audit/service.py`) and has not been touched since.

Proven red (9 October 2026): `value=contact.value` taken out of `snapshot_contact_detail` → its row differs.
"""

from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.domains.audit.api import (
    snapshot_address,
    snapshot_contact_detail,
    snapshot_member,
    snapshot_member_person,
    snapshot_person,
)
from app.domains.mdm.api import (
    CONTACT,
    AddressHistory,
    ContactDetailHistory,
    MemberHistory,
    MemberPersonHistory,
    PersonHistory,
    RelationType,
)
from tests._snapshot import recorded_history_rows

pytestmark = pytest.mark.ui_agnostisch

EXPECTED: list[tuple[str, dict]] = [
    (
        "snapshot_person",
        {
            "person_id": 883001,
            "last_name": "Voorbeeld",
            "first_name": "An",
            "date_of_birth": "1980-02-29",
            "gender_code": "F",
            "operation": "update",
            "action": "recorded_0",
            "source": "recording",
            "actor": "board@example.org",
        },
    ),
    (
        "snapshot_member",
        {
            "member_id": 883002,
            "board_member_id": 883009,
            "operation": "update",
            "action": "recorded_1",
            "source": "recording",
            "actor": "board@example.org",
        },
    ),
    (
        "snapshot_member_person",
        {
            "member_person_id": 883003,
            "member_id": 883002,
            "person_id": 883001,
            "relation_type": "HOOFDLID",
            "operation": "update",
            "action": "recorded_2",
            "source": "recording",
            "actor": "board@example.org",
        },
    ),
    (
        "snapshot_address",
        {
            "address_id": 883004,
            "person_id": 883001,
            "street": "Voorbeeldstraat",
            "house_number": "12",
            "bus_number": "B",
            "postal_code_id": 883005,
            "operation": "update",
            "action": "recorded_3",
            "source": "recording",
            "actor": "board@example.org",
        },
    ),
    (
        "snapshot_contact_detail",
        {
            "contact_detail_id": 883006,
            "person_id": 883001,
            "contact_type_code": "EMAIL",
            "value": "an@example.org",
            "is_primary": True,
            "operation": "update",
            "action": "recorded_4",
            "source": "recording",
            "actor": "board@example.org",
        },
    ),
]


def test_every_snapshot_of_mdm_writes_the_row_it_wrote(db_session):
    rows = recorded_history_rows(
        db_session,
        [
            (
                snapshot_person,
                PersonHistory,
                SimpleNamespace(
                    id=883_001,
                    last_name="Voorbeeld",
                    first_name="An",
                    date_of_birth=date(1980, 2, 29),
                    gender_code="F",
                ),
            ),
            (snapshot_member, MemberHistory, SimpleNamespace(id=883_002, board_member_id=883_009)),
            (
                snapshot_member_person,
                MemberPersonHistory,
                SimpleNamespace(
                    id=883_003,
                    member_id=883_002,
                    person_id=883_001,
                    relation_type=RelationType.PRIMARY_MEMBER,
                ),
            ),
            (
                snapshot_address,
                AddressHistory,
                SimpleNamespace(
                    id=883_004,
                    person_id=883_001,
                    street="Voorbeeldstraat",
                    house_number="12",
                    bus_number="B",
                    postal_code_id=883_005,
                ),
            ),
            (
                snapshot_contact_detail,
                ContactDetailHistory,
                SimpleNamespace(
                    id=883_006,
                    person_id=883_001,
                    contact_type_code=CONTACT.EMAIL,
                    value="an@example.org",
                    is_primary=True,
                ),
            ),
        ],
    )
    assert rows == EXPECTED
