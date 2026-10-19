"""The sales domain (CR-21, the webshop): orders, their lines, and the shop's settings.

Phase 2 gives `sales` its shape: a `SalesOrder` is a payable of `payment` (D4), its
lines carry the price fixed at the order (D3) and the variant they reserve, and the
shop's own settings and contact persons live here (F17). The screens — the Webshop,
the basket, Verkoop's list — come with the commits that follow.

`variant_id` and `person_id` are soft references (no foreign key leaves the schema,
`test_schema_boundaries`); `order_id` is a real foreign key within the schema.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.domains.mdm.api import PaymentMethod
from app.kernel.codes import EnumColumn
from app.kernel.rules import aggregate
from app.kernel.tenancy import TenantMixin
from app.soft_delete import SoftDeleteMixin


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


#: The unique index that makes a shown order form accepted once (#1987).
SUBMISSION_KEY_CONSTRAINT = "uq_sales_orders_submission_key"


class SalesError(ValueError):
    """A rule of this domain was violated. One class for the domain, English.

    `field` is the form's name of the field the refusal is about, so the door can
    mark it (#2121); "" — the default — is the form as a whole."""

    field: str = ""

    def __init__(self, *args: object, field: str = ""):
        super().__init__(*args)
        if field:
            self.field = field


class ProductHasOrderLines(SalesError):
    """A product that still has order lines cannot be deleted (T19, Q75).

    Raised by the sales handler on `ProductDeleted` for the whole-product case;
    the screen that catches it offers "Afgevoerd", as it does for a product with
    movements. A size with order lines raises `SizeDeleteRefused` instead, so the
    record names the size at its row.
    """


@aggregate
class SalesOrder(TenantMixin, SoftDeleteMixin, Base):
    """One webshop order (D6). Soft-deleted as a registration (Q61): a cancelled
    order leaves the lists and keeps its rows.

    `person_id` names the person who placed the order — the person of the typed
    address, never the seller (F18); for a guest the three `guest_*` fields carry the
    address instead. `buyer_party_id` (CR-26 F8) names who the order is for: the person's
    own party for *voor mezelf*, an organisation's for *namens*, NULL for a guest; for an
    order Verkoop enters for an organisation `person_id` may be NULL. The `buyer_*`
    columns are the copy of who that was at placement — name, address, VAT number — so
    the invoice of CR-34 reads one source; all nullable (a private person has no VAT
    number, a guest's address is asked of nobody by this change). The order's payment
    status comes from `payment`, its delivery status from its lines (R34) — no status
    column of its own.
    """

    __tablename__ = "sales_orders"
    __table_args__ = (
        # #1987: a shown order form is accepted once — the database decides, so two
        # posts at the same moment cannot both pass a check (`form_guard.is_repeat`).
        # A deleted order frees its key (review of dev1, finding 2 of the registration's
        # half): the key holds while the order lives, as the lookup sees it.
        Index(
            SUBMISSION_KEY_CONSTRAINT,
            "tenant_id",
            "submission_key",
            unique=True,
            postgresql_where=text("submission_key IS NOT NULL AND deleted_at IS NULL"),
        ),
        # The secret of the thank-you page: unique, so a link names exactly one order.
        Index("uq_sales_orders_secret_key", "secret_key", unique=True),
        {"schema": "sales"},
    )

    id = Column(Integer, primary_key=True, index=True)
    person_id = Column(Integer, nullable=True, index=True)
    guest_name = Column(String(200), nullable=True)
    guest_email = Column(String(200), nullable=True)
    guest_mobile = Column(String(200), nullable=True)
    #: A real key across schemas, by the named exception of CR-26 B4 (the schema
    #: boundary gate allows `mdm.parties`).
    buyer_party_id = Column(Integer, ForeignKey("mdm.parties.id"), nullable=True, index=True)
    buyer_name = Column(String(200), nullable=True)
    buyer_street = Column(String(200), nullable=True)
    buyer_house_number = Column(String(20), nullable=True)
    buyer_bus_number = Column(String(20), nullable=True)
    buyer_postal_code = Column(String(10), nullable=True)
    buyer_municipality = Column(String(100), nullable=True)
    buyer_country = Column(String(2), nullable=True)
    buyer_vat_number = Column(String(50), nullable=True)
    payment_method: Mapped[PaymentMethod] = mapped_column(
        EnumColumn(PaymentMethod, length=20), nullable=True
    )
    placed_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    # #1987: the key a shown order form is accepted once by — the token's signed
    # time and random part (`form_guard.submission_key`). Nothing else reads it.
    submission_key = Column(String(64), nullable=True)
    # The secret of the thank-you page's link (Koen, 16 October 2026): random and
    # unique, never shown in the back office or logged. An order placed before the
    # migration has none and has no thank-you page by link.
    secret_key = Column(String(64), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )

    lines = relationship(
        "SalesOrderLine",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="SalesOrderLine.id",
    )

    def check(self) -> None:
        """A guest's order needs the buyer's name, e-mail and mobile (A7's privacy
        row, K6): the order hangs on the person of the typed address, so without a
        person those three carry the address. An order with a buyer party but no person
        (Verkoop for an organisation, CR-26 F8) passes: the party is who it is for.
        Judged on the outcome, on the aggregate, whatever path created the order."""
        if self.person_id is not None or self.buyer_party_id is not None:
            return
        from app.i18n import _

        if not (self.guest_name or "").strip():
            raise SalesError(_("Vul je naam in."))
        if not (self.guest_email or "").strip():
            raise SalesError(_("Vul je e-mailadres in."))
        if not (self.guest_mobile or "").strip():
            raise SalesError(_("Vul je mobiele nummer in."))


class SalesOrderLine(TenantMixin, SoftDeleteMixin, Base):
    """One line of an order: the variant, how many, and the price fixed when the
    order was placed (D3, F4). `unit_code` is the UN/ECE unit of a piece, 'C62'
    (B3a). Delivering a line sets `delivered_at` and lowers the stock (F6)."""

    __tablename__ = "sales_order_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="ck_sales_order_lines_quantity_positive"),
        {"schema": "sales"},
    )

    id = Column(Integer, primary_key=True, index=True)
    order_id = Column(
        Integer, ForeignKey("sales.sales_orders.id", ondelete="CASCADE"), nullable=False, index=True
    )
    variant_id = Column(Integer, nullable=False, index=True)
    quantity = Column(Integer, nullable=False)
    unit_code = Column(String(8), nullable=False, default="C62")
    unit_price = Column(Numeric(10, 2), nullable=False)
    delivered_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )

    order = relationship("SalesOrder", back_populates="lines")


class ShopSettings(TenantMixin, Base):
    """The shop's own settings (F17, R42): one intro text per tenant."""

    __tablename__ = "shop_settings"
    __table_args__ = {"schema": "sales"}

    id = Column(Integer, primary_key=True, index=True)
    intro = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )


class ShopContact(TenantMixin, SoftDeleteMixin, Base):
    """A contact person of the shop (F17, R41): a soft reference to `mdm.persons`,
    ordered. No override of e-mail or mobile — the person's own are shown (Q71).
    Soft-deleted like the rest of the domain: removing a contact leaves the row,
    so nothing that pointed at it reads through to a gap."""

    __tablename__ = "shop_contacts"
    __table_args__ = {"schema": "sales"}

    id = Column(Integer, primary_key=True, index=True)
    person_id = Column(Integer, nullable=False, index=True)
    sort_order = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(
        DateTime(timezone=True), default=_now_utc, onupdate=_now_utc, nullable=False
    )
