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
    ReservationStatus,
    StockError,
    StockLocation,
    StockMovement,
    StockReservation,
    available,
    correct,
    issue,
    movements_of,
    on_hand,
    receive,
    release,
    reserve,
    reserved,
    waiting,
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


def test_a_correction_asks_for_a_reason(db_session):
    receive(db_session, variant_id=1, quantity=10)

    with pytest.raises(StockError):
        correct(db_session, variant_id=1, quantity=1, note="   ")


def test_reserved_is_zero_while_nothing_reserves(db_session):
    receive(db_session, variant_id=1, quantity=10)

    assert reserved(db_session, 1) == 0


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


def test_the_writer_holds_the_advisory_lock(db_session):
    """A writer of the ledger holds the transaction-scoped lock per tenant,
    variant and location (C4.1): a second connection cannot take the same key
    while the writer's transaction is open. Red when the lock is a no-op."""
    from sqlalchemy import text

    from app.database import engine
    from app.domains.stock.api import StockLocation, lock_key

    receive(db_session, variant_id=1, quantity=1)
    location = db_session.query(StockLocation).filter(StockLocation.is_default.is_(True)).one()
    key = lock_key(location.tenant_id, 1, location.id)

    with engine.connect() as conn:
        got = conn.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}).scalar()
    assert got is False, "the writer holds the lock; a second connection took it"


def test_movements_of_returns_newest_first(db_session):
    """AC16: a correction made after a receipt stands above it — the movements
    read newest first. Red with the order turned round."""
    receive(db_session, variant_id=1, quantity=10)
    correct(db_session, variant_id=1, quantity=-2, note="retour")

    assert [m.reason for m in movements_of(db_session, 1)] == [
        MovementReason.CORRECTION,
        MovementReason.RECEIPT,
    ]


def test_reserve_holds_back_and_refuses_when_short(db_session):
    """F1/R13: a reservation reduces available, not on hand, and a second reserve
    past what is left is refused."""
    receive(db_session, variant_id=1, quantity=2)
    reserve(db_session, order_line_id=1, variant_id=1, quantity=1)

    assert on_hand(db_session, 1) == 2
    assert available(db_session, 1) == 1
    assert reserved(db_session, 1) == 1

    with pytest.raises(NotEnoughStock):
        reserve(db_session, order_line_id=2, variant_id=1, quantity=2)


def test_reserve_allow_short_reserves_beyond_on_hand(db_session):
    """F15/R39: an article "Op bestelling" reserves beyond what is on hand."""
    reserve(db_session, order_line_id=1, variant_id=1, quantity=3, allow_short=True)

    assert on_hand(db_session, 1) == 0
    assert available(db_session, 1) == -3
    assert reserved(db_session, 1) == 3


def test_release_frees_the_reservation(db_session):
    """F8/R13: a cancelled reservation is no longer held back."""
    receive(db_session, variant_id=1, quantity=1)
    reserve(db_session, order_line_id=1, variant_id=1, quantity=1)
    release(db_session, order_line_id=1)

    assert available(db_session, 1) == 1
    assert reserved(db_session, 1) == 0


def test_issue_delivers_the_line(db_session):
    """F6/R21: delivering writes a GOODS_ISSUE movement and sets the reservation
    DELIVERED, so the stock goes down and the reservation closes."""
    receive(db_session, variant_id=1, quantity=2)
    reserve(db_session, order_line_id=1, variant_id=1, quantity=2)
    issue(db_session, order_line_id=1)

    assert on_hand(db_session, 1) == 0
    assert reserved(db_session, 1) == 0
    movement = db_session.query(StockMovement).filter(StockMovement.order_line_id == 1).one()
    assert movement.reason is MovementReason.GOODS_ISSUE
    assert movement.quantity == -2
    reservation = (
        db_session.query(StockReservation).filter(StockReservation.order_line_id == 1).one()
    )
    assert reservation.status is ReservationStatus.DELIVERED


def test_waiting_returns_the_lines_not_covered_oldest_first(db_session):
    """F5/Q87: on hand covers the oldest reservations first; the line whose
    reservation is beyond it is "waiting"."""
    receive(db_session, variant_id=1, quantity=3)
    reserve(db_session, order_line_id=1, variant_id=1, quantity=2)
    reserve(db_session, order_line_id=2, variant_id=1, quantity=2, allow_short=True)

    assert waiting(db_session, [1, 2]) == [2]


def test_waiting_sees_an_allow_short_reservation_as_uncovered(db_session):
    reserve(db_session, order_line_id=1, variant_id=1, quantity=3, allow_short=True)

    assert waiting(db_session, [1]) == [1]


def test_reserve_holds_the_advisory_lock(db_session):
    """C4.1: `reserve` is a writer and holds the transaction-scoped lock, so two
    orders for the last unit serialize."""
    from sqlalchemy import text

    from app.database import engine
    from app.domains.stock.api import lock_key

    reserve(db_session, order_line_id=1, variant_id=1, quantity=1, allow_short=True)
    location = db_session.query(StockLocation).filter(StockLocation.is_default.is_(True)).one()
    key = lock_key(location.tenant_id, 1, location.id)

    with engine.connect() as conn:
        got = conn.execute(text("SELECT pg_try_advisory_xact_lock(:key)"), {"key": key}).scalar()
    assert got is False, "reserve holds the lock; a second connection took it"
