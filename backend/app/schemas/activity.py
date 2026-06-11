from datetime import date, time as Time, datetime
from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel


# ── Products ──────────────────────────────────────────────────────────────────

class ProductCreate(BaseModel):
    name: str
    price: Decimal = Decimal("0.00")
    member_price: Optional[Decimal] = None
    is_free: bool = True
    max_participants: Optional[int] = None
    sort_order: int = 0


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[Decimal] = None
    member_price: Optional[Decimal] = None
    is_free: Optional[bool] = None
    max_participants: Optional[int] = None
    sort_order: Optional[int] = None


class ProductResponse(BaseModel):
    id: int
    component_id: int
    name: str
    price: Decimal
    member_price: Optional[Decimal] = None
    is_free: bool
    max_participants: Optional[int] = None
    sort_order: int

    model_config = {"from_attributes": True}


# ── Components (Onderdelen) ───────────────────────────────────────────────────

class ComponentCreate(BaseModel):
    name: str
    team_name_required: bool = False
    sort_order: int = 0
    external_register_url: Optional[str] = None
    external_registrations_url: Optional[str] = None
    info_url: Optional[str] = None
    max_participants: Optional[int] = None


class ComponentUpdate(BaseModel):
    name: Optional[str] = None
    team_name_required: Optional[bool] = None
    sort_order: Optional[int] = None
    external_register_url: Optional[str] = None
    external_registrations_url: Optional[str] = None
    info_url: Optional[str] = None
    max_participants: Optional[int] = None


class ComponentResponse(BaseModel):
    id: int
    name: str
    team_name_required: bool
    sort_order: int
    external_register_url: Optional[str] = None
    external_registrations_url: Optional[str] = None
    info_url: Optional[str] = None
    max_participants: Optional[int] = None
    products: List[ProductResponse] = []

    model_config = {"from_attributes": True}


# ── Activities ────────────────────────────────────────────────────────────────

class ActivityCreate(BaseModel):
    name: str
    date: date
    date_end: Optional[date] = None
    time: Optional[Time] = None
    location: Optional[str] = None
    poster_url: Optional[str] = None


class ActivityUpdate(BaseModel):
    name: Optional[str] = None
    date: Optional[date] = None
    date_end: Optional[date] = None
    time: Optional[Time] = None
    location: Optional[str] = None
    poster_url: Optional[str] = None
    is_cancelled: Optional[bool] = None


class ActivityResponse(BaseModel):
    id: int
    name: str
    date: date
    date_end: Optional[date] = None
    time: Optional[Time] = None
    location: Optional[str] = None
    poster_url: Optional[str] = None
    created_at: datetime
    status: Optional[str] = None
    registration_count: Optional[int] = None
    waitlist_count: Optional[int] = None
    sub_registrations: List[ComponentResponse] = []

    model_config = {"from_attributes": True}


# ── Registrations ─────────────────────────────────────────────────────────────

class RegistrationItemCreate(BaseModel):
    product_id: int
    quantity: int = 1


class RegistrationCreate(BaseModel):
    contact_name: str
    contact_email: str
    phone: Optional[str] = None
    team_name: Optional[str] = None
    payment_method: Optional[str] = None
    component_id: Optional[int] = None
    items: List[RegistrationItemCreate] = []
    remarks: Optional[str] = None


class RegistrationItemResponse(BaseModel):
    product_id: int
    quantity: int
    product_name: Optional[str] = None
    component_name: Optional[str] = None

    model_config = {"from_attributes": True}


class RegistrationResponse(BaseModel):
    id: int
    activity_id: int
    component_id: Optional[int] = None
    person_id: Optional[int] = None
    is_waitlist: bool
    registered_at: datetime
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    phone: Optional[str] = None
    team_name: Optional[str] = None
    payment_method: Optional[str] = None
    checkout_url: Optional[str] = None
    remarks: Optional[str] = None
    items: List[RegistrationItemResponse] = []

    model_config = {"from_attributes": True}


# Keep for backwards compat in router imports
SubRegistrationResponse = ComponentResponse
SubRegistrationCreate = ComponentCreate
