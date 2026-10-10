"""The stock ledger (CR-21), behind `api.py`.

Phase 1 gives the ledger its writers `receive` and `correct` and its readers
`on_hand` and `available`; `reserve`, `release` and `issue` come with phase 2.
On hand is the sum of the movements; available is that minus the open
reservations (D2). Every writer takes the same transaction-scoped advisory lock
per tenant, variant and location — "available never below zero" has no home at
rest, so the lock is its one home (C4.1).
"""

import hashlib

from sqlalchemy import func, text
from sqlalchemy.orm import Session

from app.domains.stock.models import (
    MovementReason,
    NotEnoughStock,
    ReservationStatus,
    StockError,
    StockLocation,
    StockMovement,
    StockReservation,
)

DEFAULT_LOCATION_NAME = "Magazijn"


def lock_key(tenant_id: int, variant_id: int, location_id: int) -> int:
    """A stable 64-bit key for the advisory lock of one variant at one location."""
    digest = hashlib.blake2b(
        f"{tenant_id}:{variant_id}:{location_id}".encode("ascii"), digest_size=8
    ).digest()
    return int.from_bytes(digest, "big", signed=True)


def _acquire_lock(db: Session, location: StockLocation, variant_id: int) -> None:
    db.execute(
        text("SELECT pg_advisory_xact_lock(:key)"),
        {"key": lock_key(location.tenant_id, variant_id, location.id)},
    )


def _default_location(db: Session) -> StockLocation | None:
    return db.query(StockLocation).filter(StockLocation.is_default.is_(True)).first()


def _ensure_default_location(db: Session) -> StockLocation:
    location = _default_location(db)
    if location is None:
        location = StockLocation(name=DEFAULT_LOCATION_NAME, is_default=True)
        db.add(location)
        db.flush()
    return location


def _resolve_location(db: Session, location_id: int | None) -> StockLocation | None:
    if location_id is not None:
        return db.get(StockLocation, location_id)
    return _default_location(db)


def _movements_sum(db: Session, variant_id: int, location_id: int) -> int:
    return (
        db.query(func.coalesce(func.sum(StockMovement.quantity), 0))
        .filter(
            StockMovement.variant_id == variant_id,
            StockMovement.location_id == location_id,
        )
        .scalar()
    )


def _open_reservations_sum(db: Session, variant_id: int, location_id: int) -> int:
    return (
        db.query(func.coalesce(func.sum(StockReservation.quantity), 0))
        .filter(
            StockReservation.variant_id == variant_id,
            StockReservation.location_id == location_id,
            StockReservation.status == ReservationStatus.OPEN,
        )
        .scalar()
    )


def on_hand(db: Session, variant_id: int, location_id: int | None = None) -> int:
    """What is in stock, as the sum of the movements (D2). No location at all
    means no movements, so zero."""
    location = _resolve_location(db, location_id)
    if location is None:
        return 0
    return _movements_sum(db, variant_id, location.id)


def has_movements(db: Session, variant_ids: tuple[int, ...]) -> bool:
    """Do any of these variants have a movement? The gate of a delete (Q75): an
    article with a movement is decommissioned, never deleted."""
    if not variant_ids:
        return False
    return (
        db.query(StockMovement.id).filter(StockMovement.variant_id.in_(variant_ids)).first()
        is not None
    )


def available(db: Session, variant_id: int, location_id: int | None = None) -> int:
    """What can still be sold: on hand minus the open reservations (D2)."""
    location = _resolve_location(db, location_id)
    if location is None:
        return 0
    return _movements_sum(db, variant_id, location.id) - _open_reservations_sum(
        db, variant_id, location.id
    )


def receive(
    db: Session,
    variant_id: int,
    quantity: int,
    *,
    note: str | None = None,
    actor: str | None = None,
    location_id: int | None = None,
) -> StockMovement:
    """Book a receipt from the supplier (R37): a positive RECEIPT movement.

    A tenant's default location appears on the first write (a receipt), never on
    a read.
    """
    location = (
        _ensure_default_location(db) if location_id is None else db.get(StockLocation, location_id)
    )
    if location is None:
        raise StockError("Onbekende locatie.")
    _acquire_lock(db, location, variant_id)
    if quantity <= 0:
        from app.i18n import _

        raise StockError(_("Een ontvangst boekt een positief aantal."))
    movement = StockMovement(
        variant_id=variant_id,
        location_id=location.id,
        quantity=quantity,
        reason=MovementReason.RECEIPT,
        note=note,
        actor=actor,
    )
    db.add(movement)
    db.flush()
    return movement


def correct(
    db: Session,
    variant_id: int,
    quantity: int,
    *,
    note: str,
    actor: str | None = None,
    location_id: int | None = None,
) -> StockMovement:
    """Adjust the stock by hand, up or down (R36): a signed CORRECTION movement.

    A correction down is refused when it would take "Beschikbaar" below zero
    (Q83) — available never goes below zero.
    """
    location = (
        _ensure_default_location(db) if location_id is None else db.get(StockLocation, location_id)
    )
    if location is None:
        raise StockError("Onbekende locatie.")
    _acquire_lock(db, location, variant_id)
    if quantity == 0:
        from app.i18n import _

        raise StockError(_("Een correctie moet een aantal erbij of eraf doen."))
    if quantity < 0:
        in_hand = _movements_sum(db, variant_id, location.id)
        open_reserved = _open_reservations_sum(db, variant_id, location.id)
        if in_hand - open_reserved + quantity < 0:
            raise NotEnoughStock(variant_id, in_hand - open_reserved)
    movement = StockMovement(
        variant_id=variant_id,
        location_id=location.id,
        quantity=quantity,
        reason=MovementReason.CORRECTION,
        note=note,
        actor=actor,
    )
    db.add(movement)
    db.flush()
    return movement
