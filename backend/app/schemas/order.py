from datetime import datetime
from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel


class ProductResponse(BaseModel):
    id: int
    name: str
    regular_price: Decimal
    member_price: Optional[Decimal] = None
    category: Optional[str] = None
    is_active: bool

    model_config = {"from_attributes": True}


class OrderItemCreate(BaseModel):
    product_id: int
    quantity: int


class OrderCreate(BaseModel):
    family_id: Optional[int] = None
    customer_name: str
    customer_email: str
    is_member: bool = False
    items: List[OrderItemCreate]
    notes: Optional[str] = None


class OrderItemResponse(BaseModel):
    id: int
    product_id: int
    quantity: int
    unit_price: Decimal
    product: Optional[ProductResponse] = None

    model_config = {"from_attributes": True}


class OrderResponse(BaseModel):
    id: int
    confirmation_number: str
    family_id: Optional[int] = None
    customer_name: str
    customer_email: str
    is_member: bool
    total_amount: Decimal
    payment_status: str
    mollie_payment_id: Optional[str] = None
    notes: Optional[str] = None
    created_at: datetime
    items: List[OrderItemResponse] = []

    model_config = {"from_attributes": True}
