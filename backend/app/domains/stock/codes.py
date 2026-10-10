"""The code lists the stock domain owns (CR-21): a movement's reason, a reservation's state."""

from app.domains.stock.models import (
    MovementReason,
    MovementReasonCode,
    MovementReasonLabel,
    ReservationStatus,
    ReservationStatusCode,
    ReservationStatusLabel,
)
from app.kernel.codes import CodeList, CodeSeed

MOVEMENT_REASON_CODES = (
    CodeSeed(code="RECEIPT", nl="Ontvangst", en="Receipt", sort_order=10),
    CodeSeed(code="GOODS_ISSUE", nl="Afgeleverd", en="Goods issue", sort_order=20),
    CodeSeed(code="CORRECTION", nl="Correctie", en="Correction", sort_order=30),
)

MOVEMENT_REASON = CodeList(
    name="movement_reason",
    schema="stock",
    codes=MovementReasonCode,
    labels=MovementReasonLabel,
    enum=MovementReason,
    fk_from=("stock.stock_movements.reason",),
)

RESERVATION_STATUS_CODES = (
    CodeSeed(code="OPEN", nl="Gereserveerd", en="Reserved", sort_order=10),
    CodeSeed(code="DELIVERED", nl="Afgeleverd", en="Delivered", sort_order=20),
    CodeSeed(code="CANCELLED", nl="Geannuleerd", en="Cancelled", sort_order=30),
)

RESERVATION_STATUS = CodeList(
    name="reservation_status",
    schema="stock",
    codes=ReservationStatusCode,
    labels=ReservationStatusLabel,
    enum=ReservationStatus,
    fk_from=("stock.stock_reservations.status",),
)
