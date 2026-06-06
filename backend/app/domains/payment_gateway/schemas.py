from decimal import Decimal
from typing import Optional
from pydantic import BaseModel


class PaymentRequest(BaseModel):
    amount: Decimal
    description: str
    redirect_url: str
    webhook_url: str
    metadata: dict = {}


class PaymentResponse(BaseModel):
    id: str
    provider: str
    provider_payment_id: Optional[str] = None
    checkout_url: Optional[str] = None
    status: str
    amount: Decimal

    model_config = {"from_attributes": True}


class WebhookPayload(BaseModel):
    id: str  # Mollie payment ID
