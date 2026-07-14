import uuid as uuid_lib
from datetime import datetime, timezone
from sqlalchemy import Column, String, Numeric, DateTime, Integer, ForeignKey, JSON
from sqlalchemy.orm import relationship
from app.database import Base
from app.kernel.tenancy import TenantMixin
from app.soft_delete import SoftDeleteMixin


class PaymentRecord(TenantMixin, SoftDeleteMixin, Base):
    __tablename__ = "payment_records"
    __table_args__ = {"schema": "payment"}

    id = Column(String(36), primary_key=True, default=lambda: str(uuid_lib.uuid4()))
    payable_type = Column(String(50), nullable=False, index=True)  # "registration", "membership"
    payable_id = Column(Integer, nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    method = Column(String(20), nullable=False)   # "online", "cash", "transfer"
    status = Column(String(20), default="pending", nullable=False)  # "pending", "paid", "failed", "cancelled"
    # "charge" = verschuldigd bedrag, "refund" = terugbetaling (negatief bedrag) (#83)
    type = Column(String(10), default="charge", nullable=False)
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
    provider = Column(String(20), nullable=False)         # "mollie", "stripe"
    provider_payment_id = Column(String(100), nullable=True, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    currency = Column(String(3), default="EUR", nullable=False)
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


class PaymentStatusCode(Base):
    """Codetabel (verhuisd uit app/models/codes.py, #444). Public schema."""

    __tablename__ = "payment_status_codes"
    code = Column(String(10), primary_key=True)
    language = Column(String(5), primary_key=True)
    value = Column(String(100), nullable=False)
    description = Column(String(255), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)
