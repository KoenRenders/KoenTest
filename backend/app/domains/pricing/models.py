"""Prices over time (CR-21, the webshop's `pricing` domain).

Schema ``pricing``. A price has a start date only; it ends where the next one of
the same type for the same product and variant starts (C4.2). A variant's price
overrides the product's (Q4): `variant_id` is NULL for the product's own price.
The member price is a second row with a type, never a second column (B3a).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.kernel.codes import CodeEnum, EnumColumn
from app.kernel.tenancy import TenantMixin


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class PriceError(ValueError):
    """A rule of this domain was violated. One class for the domain, English."""


class PriceType(CodeEnum):
    """Who a price is for (B3a, UNCL 5387): the regular price, or the member's."""

    REGULAR = "REGULAR"
    MEMBER = "MEMBER"


class PriceTypeCode(Base):
    """Which price types exist — the target of the foreign key."""

    __tablename__ = "price_type_codes"
    __table_args__ = {"schema": "pricing"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class PriceTypeLabel(Base):
    """The word a screen shows for a price type, per language."""

    __tablename__ = "price_type_labels"
    __table_args__ = {"schema": "pricing"}

    code = Column(String(20), ForeignKey("pricing.price_type_codes.code"), primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"), primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )


class Price(TenantMixin, Base):
    """One price, valid from its start date until the next one of the same type.

    `product_id` and `variant_id` are soft references into `product` — no
    foreign key across schemas (`test_schema_boundaries`). `variant_id` is NULL
    for the product's own price. The key that makes overlap impossible at rest —
    `UNIQUE NULLS NOT DISTINCT (tenant_id, product_id, variant_id, price_type,
    valid_from)` — stands in the migration, as migration 186 did for the media
    tags: a plain UNIQUE would let two product-level prices of one type and date
    in, because two NULL variants count as different.
    """

    __tablename__ = "prices"
    __table_args__ = (
        CheckConstraint("amount >= 0", name="ck_prices_amount_nonnegative"),
        {"schema": "pricing"},
    )

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, nullable=False, index=True)
    variant_id = Column(Integer, nullable=True, index=True)
    price_type: Mapped[PriceType] = mapped_column(
        EnumColumn(PriceType, length=20),
        ForeignKey("pricing.price_type_codes.code"),
        nullable=False,
    )
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), nullable=False, default="EUR")
    valid_from = Column(Date, nullable=False)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )
