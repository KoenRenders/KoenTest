import uuid as uuid_lib
from datetime import datetime, timezone
from sqlalchemy import Column, String, Numeric, DateTime, Integer, ForeignKey
from sqlalchemy.orm import relationship
from app.database import Base


class PaymentRecord(Base):
    __tablename__ = "payment_records"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid_lib.uuid4()))
    payable_type = Column(String(50), nullable=False, index=True)  # "membership", "activity_registration"
    payable_id = Column(Integer, nullable=False, index=True)
    amount = Column(Numeric(10, 2), nullable=False)
    method = Column(String(20), nullable=False)   # "online", "cash", "transfer"
    status = Column(String(20), default="pending", nullable=False)  # "pending", "paid", "failed", "cancelled"
    gateway_payment_id = Column(String(36), ForeignKey("gateway_payments.id"), nullable=True)
    amount_paid = Column(Numeric(10, 2), nullable=True)
    note = Column(String(200), nullable=True)
    paid_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
    updated_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc), nullable=False)

    gateway_payment = relationship("GatewayPayment")
