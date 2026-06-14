import uuid as uuid_lib
from datetime import datetime, timezone
from sqlalchemy import Column, String, Numeric, DateTime, JSON
from app.database import Base


class GatewayPayment(Base):
    __tablename__ = "gateway_payments"

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
