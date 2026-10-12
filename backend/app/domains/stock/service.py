"""The stock ledger (CR-21), behind `api.py`.

Phase 1 gave the ledger its writers `receive` and `correct` and its readers
`on_hand` and `available`. Phase 2 adds the reservation side: `reserve`,
`release` and `issue` write it, `waiting` reads it. On hand is the sum of the
movements; available is that minus the open reservations (D2). Every writer
takes the same transaction-scoped advisory lock per tenant, variant and location
— "available never below zero" has no home at rest, so the lock is its one home
(C4.1).
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


def reserved(db: Session, variant_id: int, location_id: int | None = None) -> int:
    """What open orders still hold back: the sum of the open reservations (D2).

    In phase 1 nothing reserves yet, so this reads zero; the reader exists so the
    Voorraadbeheer column is right the day `sales` fills it.
    """
    location = _resolve_location(db, location_id)
    if location is None:
        return 0
    return _open_reservations_sum(db, variant_id, location.id)


def movements_of(
    db: Session, variant_id: int, location_id: int | None = None
) -> list[StockMovement]:
    """The movements of one size, newest first (AC16): a receipt and a correction
    stand apart, each with its reason."""
    location = _resolve_location(db, location_id)
    if location is None:
        return []
    return (
        db.query(StockMovement)
        .filter(
            StockMovement.variant_id == variant_id,
            StockMovement.location_id == location.id,
        )
        .order_by(StockMovement.occurred_at.desc(), StockMovement.id.desc())
        .all()
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
    if not (note or "").strip():
        from app.i18n import _

        raise StockError(_("Een correctie vraagt een reden."))
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


def reserve(
    db: Session,
    order_line_id: int,
    variant_id: int,
    quantity: int,
    *,
    allow_short: bool = False,
    location_id: int | None = None,
) -> StockReservation:
    """Reserve a quantity of a variant for one order line (F1, R13).

    Under the advisory lock the available quantity is checked and the reservation
    written, so two orders for the last unit cannot both pass. `allow_short` lets
    an article "Op bestelling" reserve beyond what is on hand (F15, R39); then
    the reservation is one the stock does not cover until a receipt comes.
    """
    from app.i18n import _

    location = (
        _ensure_default_location(db) if location_id is None else db.get(StockLocation, location_id)
    )
    if location is None:
        raise StockError("Onbekende locatie.")
    _acquire_lock(db, location, variant_id)
    if quantity <= 0:
        raise StockError(_("Een reservering is een positief aantal."))
    if not allow_short:
        in_hand = _movements_sum(db, variant_id, location.id)
        open_reserved = _open_reservations_sum(db, variant_id, location.id)
        if in_hand - open_reserved < quantity:
            raise NotEnoughStock(variant_id, in_hand - open_reserved)
    reservation = StockReservation(
        order_line_id=order_line_id,
        variant_id=variant_id,
        location_id=location.id,
        quantity=quantity,
    )
    db.add(reservation)
    db.flush()
    return reservation


def _open_reservation(db: Session, order_line_id: int) -> StockReservation | None:
    return (
        db.query(StockReservation)
        .filter(
            StockReservation.order_line_id == order_line_id,
            StockReservation.status == ReservationStatus.OPEN,
        )
        .first()
    )


def release(db: Session, order_line_id: int) -> None:
    """Cancel the reservation of an order line (F8, R13): the article is free
    again. Nothing happens when the line has no open reservation."""
    reservation = _open_reservation(db, order_line_id)
    if reservation is None:
        return
    _acquire_lock(db, reservation.location, reservation.variant_id)
    reservation.status = ReservationStatus.CANCELLED
    db.flush()


def issue(db: Session, order_line_id: int, *, actor: str | None = None) -> None:
    """Deliver a line (F6, R21): a GOODS_ISSUE movement of its quantity and the
    reservation DELIVERED, in one transaction with the line's `delivered_at`.
    Nothing happens when the line has no open reservation."""
    reservation = _open_reservation(db, order_line_id)
    if reservation is None:
        return
    _acquire_lock(db, reservation.location, reservation.variant_id)
    movement = StockMovement(
        variant_id=reservation.variant_id,
        location_id=reservation.location_id,
        quantity=-reservation.quantity,
        reason=MovementReason.GOODS_ISSUE,
        order_line_id=order_line_id,
        actor=actor,
    )
    db.add(movement)
    reservation.status = ReservationStatus.DELIVERED
    db.flush()


def waiting(db: Session, order_line_ids: list[int]) -> list[int]:
    """The order lines whose reservation the stock on hand does not cover yet —
    the oldest reservations covered first, by reservation id ascending (F5, Q87).
    A reservation written with `allow_short` is one the stock does not cover."""
    if not order_line_ids:
        return []
    wanted = set(order_line_ids)
    requested = (
        db.query(StockReservation)
        .filter(
            StockReservation.order_line_id.in_(wanted),
            StockReservation.status == ReservationStatus.OPEN,
        )
        .all()
    )
    by_variant: dict[tuple[int, int], list[StockReservation]] = {}
    for reservation in requested:
        by_variant.setdefault((reservation.variant_id, reservation.location_id), []).append(
            reservation
        )
    uncovered: set[int] = set()
    for (variant_id, location_id), these in by_variant.items():
        on_hand = _movements_sum(db, variant_id, location_id)
        all_open = (
            db.query(StockReservation)
            .filter(
                StockReservation.variant_id == variant_id,
                StockReservation.location_id == location_id,
                StockReservation.status == ReservationStatus.OPEN,
            )
            .order_by(StockReservation.id.asc())
            .all()
        )
        remaining = on_hand
        covered: set[int] = set()
        for reservation in all_open:
            if remaining >= reservation.quantity:
                remaining -= reservation.quantity
                covered.add(reservation.id)
            else:
                break
        for reservation in these:
            if reservation.id not in covered:
                uncovered.add(reservation.order_line_id)
    return [line_id for line_id in order_line_ids if line_id in uncovered]


def _require_existing_variant(db: Session, variant_id: int) -> None:
    """The screen's door only writes for a size that exists here (Q83). `receive`
    and `correct` are shared with `sales` (phase 2), which has already resolved
    its variants, so the check belongs to the door, not to those two."""
    from app.domains.product.api import get_variant
    from app.i18n import _

    if get_variant(db, variant_id) is None:
        raise StockError(_("Deze maat bestaat niet."))


def book_receipt(
    db: Session,
    variant_id: int,
    quantity: int,
    *,
    actor: str | None = None,
    location_id: int | None = None,
) -> StockMovement:
    """The screen's door for a receipt (R37): one request, one transaction.

    The movement is written through `receive` (which `sales` also calls inside
    its own transaction in phase 2) and committed here, the one place the screen
    enters.
    """
    _require_existing_variant(db, variant_id)
    movement = receive(db, variant_id, quantity, actor=actor, location_id=location_id)
    db.commit()
    return movement


def apply_correction(
    db: Session,
    variant_id: int,
    quantity: int,
    *,
    note: str,
    actor: str | None = None,
    location_id: int | None = None,
) -> StockMovement:
    """The screen's door for a correction (R36): one request, one transaction."""
    _require_existing_variant(db, variant_id)
    movement = correct(db, variant_id, quantity, note=note, actor=actor, location_id=location_id)
    db.commit()
    return movement
