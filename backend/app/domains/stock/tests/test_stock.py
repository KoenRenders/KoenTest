"""The ledger (CR-21, phase 1, T5): on hand is the sum of the movements, a
receipt and a correction keep their reason, and a correction never takes
"Beschikbaar" below zero.

`variant_id` is a soft reference, so these tests use a made-up id and exercise
the stock domain on its own.
"""

from __future__ import annotations

import pytest

from app.domains.stock.api import (
    MovementReason,
    NotEnoughStock,
    StockError,
    StockLocation,
    StockMovement,
    available,
    correct,
    on_hand,
    receive,
)

pytestmark = pytest.mark.ui_agnostisch


def test_on_hand_is_the_sum_of_the_movements(db_session):
    receive(db_session, variant_id=1, quantity=10)
    correct(db_session, variant_id=1, quantity=-2, note="retour")

    assert on_hand(db_session, 1) == 8
    assert available(db_session, 1) == 8


def test_receipt_and_correction_keep_their_reason(db_session):
    receive(db_session, variant_id=1, quantity=10)
    correct(db_session, variant_id=1, quantity=-2, note="retour")

    movements = db_session.query(StockMovement).order_by(StockMovement.id).all()
    assert [m.reason for m in movements] == [MovementReason.RECEIPT, MovementReason.CORRECTION]


def test_a_correction_that_takes_available_below_zero_is_refused(db_session):
    receive(db_session, variant_id=1, quantity=2)

    with pytest.raises(NotEnoughStock):
        correct(db_session, variant_id=1, quantity=-5, note="retour")


def test_a_receipt_must_be_positive(db_session):
    with pytest.raises(StockError):
        receive(db_session, variant_id=1, quantity=-1)


def test_the_default_location_appears_on_the_first_write_not_on_a_read(db_session):
    assert db_session.query(StockLocation).count() == 0
    assert on_hand(db_session, 1) == 0  # a read creates nothing
    assert db_session.query(StockLocation).count() == 0

    receive(db_session, variant_id=1, quantity=1)
    locations = db_session.query(StockLocation).all()
    assert len(locations) == 1
    assert locations[0].is_default is True
