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


def test_a_negative_correction_against_a_reservation_is_refused(db_session):
    """Available never goes below zero: a reserved unit cannot be corrected away."""
    receive(db_session, variant_id=1, quantity=2)
    reserve(db_session, order_line_id=1, variant_id=1, quantity=2)

    with pytest.raises(NotEnoughStock):
        correct(db_session, variant_id=1, quantity=-1, note="retour")


def test_release_twice_changes_nothing(db_session):
    reserve(db_session, order_line_id=1, variant_id=1, quantity=1, allow_short=True)
    release(db_session, order_line_id=1)
    release(db_session, order_line_id=1)

    assert reserved(db_session, 1) == 0


def test_issue_twice_delivers_once(db_session):
    receive(db_session, variant_id=1, quantity=2)
    reserve(db_session, order_line_id=1, variant_id=1, quantity=2)
    issue(db_session, order_line_id=1)
    issue(db_session, order_line_id=1)

    assert on_hand(db_session, 1) == 0
    assert db_session.query(StockMovement).filter(StockMovement.order_line_id == 1).count() == 1


def test_issue_after_release_changes_nothing(db_session):
    reserve(db_session, order_line_id=1, variant_id=1, quantity=1, allow_short=True)
    release(db_session, order_line_id=1)
    issue(db_session, order_line_id=1)

    assert db_session.query(StockMovement).filter(StockMovement.order_line_id == 1).count() == 0
    assert on_hand(db_session, 1) == 0


def test_issue_of_a_short_reservation_without_stock_is_refused(db_session):
    """F2: a line that waits for the supplier cannot be handed over."""
    reserve(db_session, order_line_id=1, variant_id=1, quantity=3, allow_short=True)

    with pytest.raises(NotEnoughStock):
        issue(db_session, order_line_id=1)


def test_a_second_reserve_for_the_same_line_is_refused(db_session):
    """F3: one open reservation per order line."""
    reserve(db_session, order_line_id=1, variant_id=1, quantity=1, allow_short=True)

    with pytest.raises(StockError):
        reserve(db_session, order_line_id=1, variant_id=1, quantity=1, allow_short=True)


def test_the_open_reservation_index_is_there(db_session):
    from sqlalchemy import text

    row = db_session.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE schemaname = 'stock' AND indexname = 'uq_stock_reservations_open_line'"
        )
    ).first()
    assert row is not None, "the partial unique index is missing"


# ── Two committed connections (F1, F4) ────────────────────────────────────────


def _race_two(first_action, second_action):
    """Two committed writers. `first_action` writes and holds its transaction
    0.6 s; `second_action` starts meanwhile, blocks on the lock, and then acts on
    what the first committed. Returns the outcomes: "committed" or "refused"."""
    import threading
    import time
    from concurrent.futures import ThreadPoolExecutor

    from app.database import SessionLocal

    ready = threading.Event()
    outcomes: dict[str, str] = {}

    def run(name, action, leads):
        db = SessionLocal()
        try:
            if leads:
                action(db)
                ready.set()
                time.sleep(0.6)
                db.commit()
                outcomes[name] = "committed"
            else:
                assert ready.wait(timeout=10)
                try:
                    action(db)
                except NotEnoughStock:
                    db.rollback()
                    outcomes[name] = "refused"
                    return
                db.commit()
                outcomes[name] = "committed"
        finally:
            db.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(run, "first", first_action, True)
        second = pool.submit(run, "second", second_action, False)
        first.result()
        second.result()
    return outcomes


def _committed_stock(variant_id: int, quantity: int) -> None:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        receive(db, variant_id=variant_id, quantity=quantity)
        db.commit()
    finally:
        db.close()


def _clean_variant(variant_id: int) -> None:
    from app.database import SessionLocal

    db = SessionLocal()
    try:
        db.query(StockMovement).filter(StockMovement.variant_id == variant_id).delete(
            synchronize_session=False
        )
        db.query(StockReservation).filter(StockReservation.variant_id == variant_id).delete(
            synchronize_session=False
        )
        db.commit()
    finally:
        db.close()


def _read(db, variant_id: int) -> tuple[int, int, int]:
    return (
        on_hand(db, variant_id),
        reserved(db, variant_id),
        available(db, variant_id),
    )


def test_two_committed_reservations_for_the_last_unit_one_is_refused():
    variant_id = 71_001
    _committed_stock(variant_id, 1)
    try:

        def first(db):
            reserve(db, order_line_id=91_001, variant_id=variant_id, quantity=1)

        def second(db):
            reserve(db, order_line_id=91_002, variant_id=variant_id, quantity=1)

        outcomes = _race_two(first, second)
        assert outcomes == {"first": "committed", "second": "refused"}

        from app.database import SessionLocal

        db = SessionLocal()
        try:
            assert _read(db, variant_id) == (1, 1, 0)
        finally:
            db.close()
    finally:
        _clean_variant(variant_id)


def test_two_committed_issues_of_one_line_deliver_once():
    variant_id = 71_002
    _committed_stock(variant_id, 2)
    reserve_line = 91_003
    try:
        from app.database import SessionLocal

        db = SessionLocal()
        try:
            reserve(db, order_line_id=reserve_line, variant_id=variant_id, quantity=2)
            db.commit()
        finally:
            db.close()

        def issue_line(db):
            issue(db, order_line_id=reserve_line)

        outcomes = _race_two(issue_line, issue_line)
        assert outcomes == {"first": "committed", "second": "committed"}

        db = SessionLocal()
        try:
            assert on_hand(db, variant_id) == 0
            movements = (
                db.query(StockMovement).filter(StockMovement.order_line_id == reserve_line).count()
            )
            assert movements == 1, "one line issued twice wrote two movements"
        finally:
            db.close()
    finally:
        _clean_variant(variant_id)


def test_a_release_does_not_undo_a_committed_issue_and_vice_versa():
    for lead in ("issue", "release"):
        variant_id = 71_003 if lead == "issue" else 71_004
        _committed_stock(variant_id, 2)
        reserve_line = 91_004 if lead == "issue" else 91_005
        try:
            from app.database import SessionLocal

            db = SessionLocal()
            try:
                reserve(db, order_line_id=reserve_line, variant_id=variant_id, quantity=2)
                db.commit()
            finally:
                db.close()

            def issue_line(db):
                issue(db, order_line_id=reserve_line)

            def release_line(db):
                release(db, order_line_id=reserve_line)

            if lead == "issue":
                first, second = issue_line, release_line
            else:
                first, second = release_line, issue_line

            _race_two(first, second)

            db = SessionLocal()
            try:
                movement_count = (
                    db.query(StockMovement)
                    .filter(StockMovement.order_line_id == reserve_line)
                    .count()
                )
                status = (
                    db.query(StockReservation)
                    .filter(StockReservation.order_line_id == reserve_line)
                    .one()
                    .status
                )
                if lead == "issue":
                    assert movement_count == 1 and status is ReservationStatus.DELIVERED
                else:
                    assert movement_count == 0 and status is ReservationStatus.CANCELLED
            finally:
                db.close()
        finally:
            _clean_variant(variant_id)
