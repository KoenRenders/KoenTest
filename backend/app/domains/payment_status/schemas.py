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
    note: Optional[str] = None
    paid_at: Optional[datetime] = None
    checkout_url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class EnrichedPaymentRecord(PaymentRecordResponse):
    description: Optional[str] = None
    contact_name: Optional[str] = None


class PaymentRecordUpdate(BaseModel):
    status: Optional[str] = None
    amount_paid: Optional[Decimal] = None
    note: Optional[str] = None


MEMBERSHIP_PRICE_FULL = Decimal("35.00")
MEMBERSHIP_PRICE_HALF = Decimal("17.50")
