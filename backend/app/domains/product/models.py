"""The catalogue (CR-21, the webshop's `product` domain).

Schema ``product``. Master data, kept apart from any activity (R2): a `Product`
is one article the shop sells, a `ProductVariant` is one of its sizes, and a
`ProductAttachment` points at a picture or a document in the media library.

Three shapes decide everything here:

- **A size is a variant, and its properties are repeatable.** The size lives in
  `properties` as a list of name/value pairs (``[{"name": "Maat", "value":
  "M"}]``), as UBL's `AdditionalItemProperty`; a second axis (colour) is one
  more entry in the list, never a column (B3a).
- **One life cycle for the whole article, none per size.** A product is
  CONCEPT, ON_SALE or DISCONTINUED — a code list, so a state can be added later
  (Q74). The allowed changes are checked on the aggregate; there is no per-size
  state.
- **Pictures and documents live in the media library.** `ProductAttachment`
  points at a `media_assets` row (a soft reference across schemas); its kind is
  the asset's. The bytes never live here (D7).
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.kernel.codes import CodeEnum, EnumColumn
from app.kernel.rules import aggregate
from app.kernel.tenancy import TenantMixin


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


class ProductError(ValueError):
    """A rule of this domain was violated. One class for the domain, English.

    Not an HTTPException: that belongs to the entrance, not to the rule.
    """


class ProductStatus(CodeEnum):
    """The life cycle of an article (Q74): Concept → In verkoop → Afgevoerd.

    Member names are English; the values are the codes as stored, unchanged.
    """

    CONCEPT = "CONCEPT"
    ON_SALE = "ON_SALE"
    DISCONTINUED = "DISCONTINUED"


class ProductStatusCode(Base):
    """Which product statuses exist — the target of the foreign key."""

    __tablename__ = "product_status_codes"
    __table_args__ = {"schema": "product"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class ProductStatusLabel(Base):
    """The word a screen shows for a product status, per language."""

    __tablename__ = "product_status_labels"
    __table_args__ = {"schema": "product"}

    code = Column(String(20), ForeignKey("product.product_status_codes.code"), primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"), primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )


@aggregate
class Product(TenantMixin, Base):
    """One article the shop sells (R1, R2).

    Its rule, on the aggregate so it holds on every flush (§B4.2):

    - **never back to Concept** (Q74) — `check()`. The rule needs the previous
      value, which SQLAlchemy's attribute history already holds, so it reads
      only what is loaded and never queries.
    """

    __tablename__ = "products"
    __table_args__ = {"schema": "product"}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status: Mapped[ProductStatus] = mapped_column(
        EnumColumn(ProductStatus, length=20),
        ForeignKey("product.product_status_codes.code"),
        nullable=False,
        default=ProductStatus.CONCEPT,
    )
    # Ordering in advance (R39): the article may be ordered before there is
    # stock. `pre_order_until` is the last day of that window; empty means the
    # window has no end.
    pre_order = Column(Boolean, nullable=False, default=False)
    pre_order_until = Column(Date, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )

    variants = relationship(
        "ProductVariant",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductVariant.sort_order",
    )
    attachments = relationship(
        "ProductAttachment",
        back_populates="product",
        cascade="all, delete-orphan",
        order_by="ProductAttachment.sort_order",
    )

    def check(self) -> None:
        """The life cycle never walks back to Concept (Q74).

        Reads only the attribute's own history — a change to CONCEPT whose
        previous value was something else is the refusal. A new article starts
        at CONCEPT, so a first save has no previous value and passes.
        """
        from sqlalchemy import inspect

        history = inspect(self).attrs.status.history
        if history.has_changes() and history.deleted and self.status is ProductStatus.CONCEPT:
            from app.i18n import _

            raise ProductError(
                _("Een artikel dat al in verkoop is geweest, kan niet terug naar concept.")
            )


class ProductVariant(TenantMixin, Base):
    """One size of an article (Q1). The seller's code (`sku`) is unique per
    tenant; the size itself is the repeatable `properties` list (B3a)."""

    __tablename__ = "product_variants"
    __table_args__ = (
        UniqueConstraint("tenant_id", "sku", name="uq_product_variants_sku"),
        {"schema": "product"},
    )

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(
        Integer,
        ForeignKey("product.products.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    sku = Column(String(64), nullable=True)
    properties = Column(JSON, nullable=False, default=list)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )

    product = relationship("Product", back_populates="variants")


class ProductAttachment(TenantMixin, Base):
    """A picture or a document shown on the article, from the media library.

    `media_asset_id` is a soft reference across schemas (B3a); the asset's kind
    says whether it is a picture or a document. The bytes never live here.
    """

    __tablename__ = "product_attachments"
    __table_args__ = {"schema": "product"}

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(
        Integer,
        ForeignKey("product.products.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    media_asset_id = Column(Integer, nullable=False, index=True)
    title = Column(String(255), nullable=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )

    product = relationship("Product", back_populates="attachments")
