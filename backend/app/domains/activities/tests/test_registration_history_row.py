"""The history row of a corrected registration is what it was (CR-14 phase 3, #1334).

Phase 3 moves the writer of `activities.registration_history` from `audit`
(`snapshot_registration`, a foreign write both CR-13 ratchets listed) to its owner,
`activities.service.record_registration_history`. The move must change nothing:
this test was written and run green on the code BEFORE the move (audit's writer),
and must stay green after it — the same columns, the same values, the same action
code, one row for one real change and none for a save without one. The only
difference after the move is the new `answers` column, empty on such a row.
"""

from __future__ import annotations

import pytest

from app.domains.activities import service
from app.domains.activities.api import Registration, RegistrationHistory
from tests.conftest import seed_activity_with_product

pytestmark = pytest.mark.ui_agnostisch

#: Every column of the row except those the database hands out — and `answers`,
#: the column phase 3 adds (migration 177), checked apart: it did not exist when
#: this test was recorded, and a contact correction leaves it empty.
_GENERATED = {"id", "recorded_at", "tenant_id", "answers"}


def _rows(db, registration_id: int) -> list[dict]:
    rows = (
        db.query(RegistrationHistory)
        .filter(RegistrationHistory.registration_id == registration_id)
        .order_by(RegistrationHistory.id)
        .all()
    )
    return [
        {c.key: getattr(r, c.key) for c in r.__table__.columns if c.key not in _GENERATED}
        for r in rows
    ]


def test_a_correction_writes_the_row_it_always_wrote(db_session):
    activity, component, _product = seed_activity_with_product(db_session)
    registration = Registration(
        activity_id=activity.id,
        component_id=component.id,
        registration_type="INDIVIDUAL",
        contact_name="Rij Voor",
        contact_email="rij@example.com",
        phone="0470000000",
    )
    db_session.add(registration)
    db_session.commit()

    service.update_registration_contact(
        db_session,
        activity.id,
        registration.id,
        {"phone": "0470111111", "remarks": "  Komt later  "},
        actor="bestuur@example.com",
    )
    # A save without a difference writes nothing.
    service.update_registration_contact(
        db_session, activity.id, registration.id, {"phone": "0470111111"}, actor="x"
    )

    assert _rows(db_session, registration.id) == [
        {
            "registration_id": registration.id,
            "contact_name": "Rij Voor",
            "contact_email": "rij@example.com",
            "phone": "0470111111",
            "remarks": "Komt later",
            "operation": "update",
            "action": "registration_contact_updated",
            "source": "admin_manual",
            "actor": "bestuur@example.com",
        }
    ]
    [row] = db_session.query(RegistrationHistory).filter_by(registration_id=registration.id)
    assert row.answers is None
