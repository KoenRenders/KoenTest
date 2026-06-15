from datetime import datetime
from decimal import Decimal
from typing import Optional
from pydantic import BaseModel


class PaymentRecordCreate(BaseModel):
    payable_type: str
    payable_id: int
    amount: Decimal
    method: str  # "online", "cash", "transfer"
    redirect_url: Optional[str] = None
    description: Optional[str] = None


class PaymentRecordResponse(BaseModel):
    id: str
    payable_type: str
    payable_id: int
    amount: Decimal
    amount_paid: Optional[Decimal] = None
    method: str
    status: str
    type: str = "charge"
    refund_of_id: Optional[str] = None
    note: Optional[str] = None
    paid_at: Optional[datetime] = None
    checkout_url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class RefundCreate(BaseModel):
    """Terugbetaling op een charge-record. ``amount`` is het positieve te
    refunden bedrag; de service slaat het op als negatief record."""
    amount: Decimal
    note: Optional[str] = None
    method: str = "transfer"


class RegistrationBalance(BaseModel):
    total_due: Decimal
    total_paid: Decimal
    total_refunded: Decimal
    balance: Decimal


class EnrichedPaymentRecord(PaymentRecordResponse):
    description: Optional[str] = None
    contact_name: Optional[str] = None
    activity_id: Optional[int] = None
    component_id: Optional[int] = None      # voor de penningmeester-filter (#90)
    component_name: Optional[str] = None
    items: list = []


class PaymentRecordUpdate(BaseModel):
    status: Optional[str] = None
    amount_paid: Optional[Decimal] = None
    note: Optional[str] = None


