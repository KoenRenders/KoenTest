"""Stock as a ledger (CR-21, the webshop's `stock` domain).

Schema ``stock``. On hand is the sum of movements; a reservation is kept apart
(D2): ``available = on hand − open reservations``, per variant and location. A
movement says why it happened (a receipt, a goods issue, a correction), so the
ledger can carry a value later (R8); a count is a correction row, a goods issue
is the delivered line (R21), a receipt is what came in (R37).

No foreign key leaves the schema (`test_schema_boundaries`): ``variant_id`` and
``order_line_id`` are soft references into `product` and `sales`.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.kernel.codes import CodeEnum, EnumColumn
from app.kernel.tenancy import TenantMixin


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class StockError(ValueError):
    """A rule of this domain was violated. One class for the domain, English."""


class NotEnoughStock(StockError):
    """There is not enough of a variant available to do what was asked (F1).

    Carries the variant and the quantity available, so a screen can say how much
    is left rather than only that the move was refused.
    """

    def __init__(self, variant_id: int, available: int):
        from app.i18n import _

        self.variant_id = variant_id
        self.available = available
        super().__init__(_("Onvoldoende voorraad beschikbaar."))


class MovementReason(CodeEnum):
    """Why a movement happened (F9): RECEIPT in, GOODS_ISSUE out, CORRECTION by hand."""

    RECEIPT = "RECEIPT"
    GOODS_ISSUE = "GOODS_ISSUE"
    CORRECTION = "CORRECTION"


class ReservationStatus(CodeEnum):
    """The state of a reservation: OPEN until delivered or cancelled."""

    OPEN = "OPEN"
    DELIVERED = "DELIVERED"
    CANCELLED = "CANCELLED"


class MovementReasonCode(Base):
    """Which movement reasons exist — the target of the foreign key."""

    __tablename__ = "movement_reason_codes"
    __table_args__ = {"schema": "stock"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class MovementReasonLabel(Base):
    """The word a screen shows for a movement reason, per language."""

    __tablename__ = "movement_reason_labels"
    __table_args__ = {"schema": "stock"}

    code = Column(String(20), ForeignKey("stock.movement_reason_codes.code"), primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"), primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )


class ReservationStatusCode(Base):
    """Which reservation statuses exist — the target of the foreign key."""

    __tablename__ = "reservation_status_codes"
    __table_args__ = {"schema": "stock"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class ReservationStatusLabel(Base):
    """The word a screen shows for a reservation status, per language."""

    __tablename__ = "reservation_status_labels"
    __table_args__ = {"schema": "stock"}

    code = Column(String(20), ForeignKey("stock.reservation_status_codes.code"), primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"), primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )


class StockLocation(TenantMixin, Base):
    """A place that holds stock (R7). A tenant has one default location; it is
    created on the first write, never on a read. The key that keeps one default
    per tenant — `UNIQUE (tenant_id) WHERE is_default` — stands in the migration."""

    __tablename__ = "stock_locations"
    __table_args__ = {"schema": "stock"}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    is_default = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )


class StockMovement(TenantMixin, Base):
    """One thing that happened to a variant's stock (B3a, EPCIS's event shape).

    The quantity is signed and never zero. `variant_id` and `order_line_id` are
    soft references (the variant into `product`, the delivered line into
    `sales`); `location_id` is a real foreign key, within the schema.
    """

    __tablename__ = "stock_movements"
    __table_args__ = (
        CheckConstraint("quantity <> 0", name="ck_stock_movements_quantity_not_zero"),
        {"schema": "stock"},
    )

    id = Column(Integer, primary_key=True, index=True)
    variant_id = Column(Integer, nullable=False, index=True)
    location_id = Column(
        Integer,
        ForeignKey("stock.stock_locations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity = Column(Integer, nullable=False)
    reason: Mapped[MovementReason] = mapped_column(
        EnumColumn(MovementReason, length=20),
        ForeignKey("stock.movement_reason_codes.code"),
        nullable=False,
    )
    occurred_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    order_line_id = Column(Integer, nullable=True, index=True)
    note = Column(Text, nullable=True)
    actor = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )

    location = relationship("StockLocation")


class StockReservation(TenantMixin, Base):
    """A committed quantity of a variant, kept apart from the movements (D2).

    `order_line_id` is a soft reference into `sales`; the reservation holds the
    stock while the order is open, and is released or delivered later.
    """

    __tablename__ = "stock_reservations"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_stock_reservations_quantity_positive"),
        {"schema": "stock"},
    )

    id = Column(Integer, primary_key=True, index=True)
    order_line_id = Column(Integer, nullable=True, index=True)
    variant_id = Column(Integer, nullable=False, index=True)
    location_id = Column(
        Integer,
        ForeignKey("stock.stock_locations.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    quantity = Column(Integer, nullable=False)
    status: Mapped[ReservationStatus] = mapped_column(
        EnumColumn(ReservationStatus, length=20),
        ForeignKey("stock.reservation_status_codes.code"),
        nullable=False,
        default=ReservationStatus.OPEN,
    )
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )

    location = relationship("StockLocation")
