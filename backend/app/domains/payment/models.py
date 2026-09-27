import uuid as uuid_lib
from datetime import datetime, timezone
from enum import Enum
from sqlalchemy import (
    JSON, Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base
from app.domains.mdm.api import PaymentMethod
from app.kernel.codes import EnumColumn
from app.kernel.tenancy import TenantMixin
from app.soft_delete import SoftDeleteMixin


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ── The vocabularies of this domain (CR-12 phase 1) ──────────────────────────
#
# Plain `Enum`, never `str, Enum`: with a `str` subclass `record.status ==
# "paid"` stays a valid comparison that happens to be true, so a stale literal
# survives unnoticed. Plain, it is silently false — which is why the migration
# of this phase had to replace every one of them at once rather than one at a
# time. Member names are English; the values are the codes exactly as they are
# stored today (§B4.3, R8).


class PaymentStatus(Enum):
    """Where a payment record stands. Four codes, unchanged since #83."""

    PENDING = "pending"
    PAID = "paid"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PaymentType(Enum):
    """A claim or its reversal (#83).

    `charge` is money owed, `refund` is money going back — a separate record
    with a negative amount, pointing at the charge it reverses.
    """

    CHARGE = "charge"
    REFUND = "refund"


class PayableType(Enum):
    """What the money is *for*: the polymorphic half of the ledger.

    The pair (`payable_type`, `payable_id`) is how a payment record points at a
    registration or a membership without a foreign key to either — the ledger
    serves two domains and may not depend on both.
    """

    REGISTRATION = "registration"
    MEMBERSHIP = "membership"


class PaymentProvider(Enum):
    """Which payment service providers we support.

    Ours, not theirs — which is the whole distinction of §B4.10. *Which*
    providers exist is our decision and our code branches on it, so it gets a
    code table. The statuses those providers report do not: see
    `providers/mollie.py`.
    """

    MOLLIE = "mollie"


class PaymentStatusCode(Base):
    __tablename__ = "payment_status_codes"
    __table_args__ = {"schema": "payment"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class PaymentStatusLabel(Base):
    __tablename__ = "payment_status_labels"
    __table_args__ = {"schema": "payment"}

    code = Column(String(20), ForeignKey("payment.payment_status_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


class PaymentTypeCode(Base):
    __tablename__ = "payment_type_codes"
    __table_args__ = {"schema": "payment"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class PaymentTypeLabel(Base):
    __tablename__ = "payment_type_labels"
    __table_args__ = {"schema": "payment"}

    code = Column(String(20), ForeignKey("payment.payment_type_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


class PayableTypeCode(Base):
    __tablename__ = "payable_type_codes"
    __table_args__ = {"schema": "payment"}

    code = Column(String(50), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class PayableTypeLabel(Base):
    __tablename__ = "payable_type_labels"
    __table_args__ = {"schema": "payment"}

    code = Column(String(50), ForeignKey("payment.payable_type_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


class PaymentProviderCode(Base):
    __tablename__ = "payment_provider_codes"
    __table_args__ = {"schema": "payment"}

    code = Column(String(20), primary_key=True)
    sort_order = Column(Integer, nullable=False, default=0)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)


class PaymentProviderLabel(Base):
    __tablename__ = "payment_provider_labels"
    __table_args__ = {"schema": "payment"}

    code = Column(String(20), ForeignKey("payment.payment_provider_codes.code"),
                  primary_key=True)
    language = Column(String(5), ForeignKey("mdm.language_codes.code"),
                      primary_key=True)
    value = Column(String(150), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=_now_utc, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=_now_utc, onupdate=_now_utc,
                        nullable=False)


class PaymentRecord(TenantMixin, SoftDeleteMixin, Base):
    __tablename__ = "payment_records"
    __table_args__ = {"schema": "payment"}

    id = Column(String(36), primary_key=True, default=lambda: str(uuid_lib.uuid4()))
    # The four vocabulary columns, as `Mapped[]` + `EnumColumn` (§B4.8). They
    # sit next to the legacy `Column()` attributes below, which is supported and
    # is what lets mypy see these four attributes' types at all. `EnumColumn`
    # writes `member.value`, so the column still holds `paid`, never `PAID`.
    payable_type: Mapped[PayableType] = mapped_column(
        EnumColumn(PayableType, length=50), nullable=False, index=True)
    payable_id = Column(Integer, nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    method: Mapped[PaymentMethod] = mapped_column(
        EnumColumn(PaymentMethod, length=20), nullable=False)
    status: Mapped[PaymentStatus] = mapped_column(
        EnumColumn(PaymentStatus, length=20), nullable=False,
        default=PaymentStatus.PENDING)
    type: Mapped[PaymentType] = mapped_column(
        EnumColumn(PaymentType, length=10), nullable=False,
        default=PaymentType.CHARGE)
    # Een refund verwijst naar de charge die het terugdraait (self-FK).
    refund_of_id = Column(String(36), ForeignKey("payment.payment_records.id"), nullable=True)
    gateway_payment_id = Column(String(36), ForeignKey("payment.gateway_payments.id"), nullable=True)
    amount_paid = Column(Numeric(10, 2), nullable=True)
    note = Column(String(200), nullable=True)
    structured_communication = Column(String(20), nullable=True)  # OGM voor overschrijving (#157)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    gateway_payment = relationship("GatewayPayment")
    refund_of = relationship("PaymentRecord", remote_side=[id])


class GatewayPayment(TenantMixin, SoftDeleteMixin, Base):
    __tablename__ = "gateway_payments"
    __table_args__ = {"schema": "payment"}

    id = Column(String(36), primary_key=True, default=lambda: str(uuid_lib.uuid4()))
    provider: Mapped[PaymentProvider] = mapped_column(
        EnumColumn(PaymentProvider, length=20), nullable=False)
    provider_payment_id = Column(String(100), nullable=True, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="EUR", nullable=False)
    # Deliberately a bare string, and deliberately no code table (§B4.10): this
    # is Mollie's vocabulary. Mollie can add a value without our migration, and
    # a foreign key here would make the webhook fail at exactly the wrong
    # moment. `providers/mollie.py` holds an `ExternalVocabulary` enum for the
    # values the adapter knows and maps them to our `PaymentStatus`.
    status = Column(String(20), default="pending", nullable=False)
    checkout_url = Column(String(500), nullable=True)
    description = Column(String(200), nullable=True)
    payment_metadata = Column(JSON, nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)


class PaymentRecordHistory(TenantMixin, Base):
    """Append-only audit van PaymentRecords (#84-patroon; geen FK's — history
    overleeft de bron)."""

    __tablename__ = "payment_record_history"
    __table_args__ = {"schema": "payment"}

    id = Column(Integer, primary_key=True, index=True)
    operation = Column(String(10), nullable=False)
    action = Column(String(40), nullable=False)
    source = Column(String(30), nullable=False)
    actor = Column(String(255), nullable=True)
    recorded_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False, index=True)

    payment_record_id = Column(String(36), nullable=False, index=True)
    payable_type = Column(String(50), nullable=True)
    payable_id = Column(Integer, nullable=True)
    amount = Column(Numeric(10, 2), nullable=True)
    amount_paid = Column(Numeric(10, 2), nullable=True)
    method = Column(String(20), nullable=True)
    status = Column(String(20), nullable=True)
    type = Column(String(10), nullable=True)          # charge / refund (#83)
    refund_of_id = Column(String(36), nullable=True)  # charge die deze refund terugdraait (#83)
    gateway_payment_id = Column(String(36), nullable=True)
    note = Column(String(200), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)

