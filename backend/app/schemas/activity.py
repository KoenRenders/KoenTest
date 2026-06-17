from __future__ import annotations
from datetime import date as Date, time as Time, datetime
from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel, EmailStr, Field, field_validator


def _non_negative_price(v: Optional[Decimal]) -> Optional[Decimal]:
    """Weiger negatieve prijzen al op vorm-niveau (nette 422) — naast de
    DB-constraint CHECK (price >= 0) als laatste vangnet."""
    if v is not None and v < 0:
        raise ValueError("prijs mag niet negatief zijn")
    return v


# ── Products ──────────────────────────────────────────────────────────────────

class ProductCreate(BaseModel):
    name: str
    price: Decimal = Decimal("0.00")
    member_price: Optional[Decimal] = None
    is_free: bool = True
    max_participants: Optional[int] = None
    sort_order: int = 0

    _v_price = field_validator("price", "member_price")(_non_negative_price)


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    price: Optional[Decimal] = None
    member_price: Optional[Decimal] = None
    is_free: Optional[bool] = None
    max_participants: Optional[int] = None
    sort_order: Optional[int] = None

    _v_price = field_validator("price", "member_price")(_non_negative_price)


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
    info_asset_url: Optional[str] = None
    info_asset_is_pdf: bool = False
    max_participants: Optional[int] = None
    products: List[ProductResponse] = []

    model_config = {"from_attributes": True}


# ── Activity dates ────────────────────────────────────────────────────────────

class ActivityDateCreate(BaseModel):
    start_date: Date
    end_date: Optional[Date] = None
    start_time: Optional[Time] = None
    end_time: Optional[Time] = None


class ActivityDateUpdate(BaseModel):
    start_date: Optional[Date] = None
    end_date: Optional[Date] = None
    start_time: Optional[Time] = None
    end_time: Optional[Time] = None


class ActivityDateResponse(BaseModel):
    id: int
    activity_id: int
    start_date: Date
    end_date: Optional[Date] = None
    start_time: Optional[Time] = None
    end_time: Optional[Time] = None

    model_config = {"from_attributes": True}


# ── Activities ────────────────────────────────────────────────────────────────

class ActivityCreate(BaseModel):
    name: str
    dates: List[ActivityDateCreate] = Field(min_length=1)
    location: Optional[str] = None
    poster_url: Optional[str] = None
    members_only: Optional[bool] = None


class ActivityUpdate(BaseModel):
    name: Optional[str] = None
    location: Optional[str] = None
    poster_url: Optional[str] = None
    is_cancelled: Optional[bool] = None
    members_only: Optional[bool] = None


class ActivityResponse(BaseModel):
    id: int
    name: str
    sort_date: Optional[Date] = None
    dates: List[ActivityDateResponse] = []
    location: Optional[str] = None
    poster_url: Optional[str] = None
    poster_asset_url: Optional[str] = None
    poster_asset_is_pdf: bool = False
    members_only: bool = False
    is_cancelled: bool = False
    created_at: datetime
    status: Optional[str] = None
    registration_count: Optional[int] = None
    sub_registrations: List[ComponentResponse] = []

    model_config = {"from_attributes": True}


# ── Registrations ─────────────────────────────────────────────────────────────

class RegistrationItemCreate(BaseModel):
    product_id: int
    quantity: int = 1


class RegistrationItemUpdate(BaseModel):
    """Admin past een bestaande bestelregel aan (#84): product wisselen en/of
    aantal wijzigen. Beide optioneel; minstens één is zinvol."""
    product_id: Optional[int] = None
    quantity: Optional[int] = None


class RegistrationCreate(BaseModel):
    contact_name: str
    contact_email: EmailStr
    phone: Optional[str] = None
    team_name: Optional[str] = None
    payment_method: Optional[str] = None
    component_id: Optional[int] = None
    items: List[RegistrationItemCreate] = []
    remarks: Optional[str] = None


class RegistrationItemResponse(BaseModel):
    id: Optional[int] = None  # registratie-item-id, nodig om regels te bewerken (#84)
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
