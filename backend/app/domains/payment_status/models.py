import uuid as uuid_lib
from datetime import datetime, timezone
from sqlalchemy import Column, String, Numeric, DateTime, Integer, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class PaymentRecord(Base):
    __tablename__ = "payment_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid_lib.uuid4()))
    payable_type = Column(String(50), nullable=False, index=True)  # "registration", "membership"
    payable_id = Column(Integer, nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    method = Column(String(20), nullable=False)   # "online", "cash", "transfer"
    status = Column(String(20), default="pending", nullable=False)  # "pending", "paid", "failed", "cancelled"
    # "charge" = verschuldigd bedrag, "refund" = terugbetaling (negatief bedrag) (#83)
    type = Column(String(10), default="charge", nullable=False)
    # Een refund verwijst naar de charge die het terugdraait (self-FK).
    refund_of_id = Column(String(36), ForeignKey("payment_records.id"), nullable=True)
    gateway_payment_id = Column(String(36), ForeignKey("gateway_payments.id"), nullable=True)
    amount_paid = Column(Numeric(10, 2), nullable=True)
    note = Column(String(200), nullable=True)
    structured_communication = Column(String(20), nullable=True)  # OGM voor overschrijving (#157)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    gateway_payment = relationship("GatewayPayment")
    refund_of = relationship("PaymentRecord", remote_side=[id])
