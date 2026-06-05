from datetime import date, time as Time, datetime
from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel, EmailStr, Field


class ActivityCreate(BaseModel):
    name: str
    date: date
    time: Optional[Time] = None
    location: Optional[str] = None
    max_participants: Optional[int] = None
    registration_type_code: str = "INDIVIDUAL"
    price: Decimal = Decimal("0.00")
    member_price: Optional[Decimal] = None
    poster_url: Optional[str] = None


class ActivityUpdate(BaseModel):
    name: Optional[str] = None
    date: Optional[date] = None
    date_end: Optional[date] = None
    time: Optional[Time] = None
    location: Optional[str] = None
    max_participants: Optional[int] = None
    registration_type_code: Optional[str] = None
    reg_form_type: Optional[str] = None
    price: Optional[Decimal] = None
    member_price: Optional[Decimal] = None
    poster_url: Optional[str] = None
    is_archived: Optional[bool] = None


class SubRegistrationCreate(BaseModel):
    name: str
    description: Optional[str] = None
    external_register_url: Optional[str] = None
    external_registrations_url: Optional[str] = None
    info_url: Optional[str] = None
    is_free: bool = True
    price: Decimal = Decimal("0.00")
    member_price: Optional[Decimal] = None
    max_participants: Optional[int] = None
    reg_form_type: Optional[str] = None
    sort_order: int = 0


class SubRegistrationUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    external_register_url: Optional[str] = None
    external_registrations_url: Optional[str] = None
    info_url: Optional[str] = None
    is_free: Optional[bool] = None
    price: Optional[Decimal] = None
    member_price: Optional[Decimal] = None
    max_participants: Optional[int] = None
    reg_form_type: Optional[str] = None
    sort_order: Optional[int] = None


class SubRegistrationResponse(BaseModel):
    id: int
    name: str
    description: Optional[str] = None
    external_register_url: Optional[str] = None
    external_registrations_url: Optional[str] = None
    info_url: Optional[str] = None
    is_free: bool
    price: Decimal
    sort_order: int
    reg_form_type: Optional[str] = None

    model_config = {"from_attributes": True}


class ActivityResponse(BaseModel):
    id: int
    name: str
    date: date
    date_end: Optional[date] = None
    time: Optional[Time] = None
    location: Optional[str] = None
    max_participants: Optional[int] = None
    registration_type_code: str
    price: Decimal
    member_price: Optional[Decimal] = None
    poster_url: Optional[str] = None
    is_archived: bool
    created_at: datetime
    status: Optional[str] = None
    registration_count: Optional[int] = None
    waitlist_count: Optional[int] = None
    sub_registrations: List[SubRegistrationResponse] = []
    reg_form_type: str = "NONE"
    age_category_config: Optional[str] = None

    model_config = {"from_attributes": True}


class RegistrationItemCreate(BaseModel):
    sub_registration_id: int
    quantity: int = 1


class RegistrationCreate(BaseModel):
    contact_name: Optional[str] = None
    contact_email: Optional[EmailStr] = None
    contact_phone: Optional[str] = None
    team_name: Optional[str] = None
    group_size: Optional[int] = Field(None, ge=1, le=500)
    age_categories: Optional[str] = None  # JSON string
    remarks: Optional[str] = None
    payment_method: Optional[str] = "FREE"
    items: List[RegistrationItemCreate] = []
    sub_registration_id: Optional[int] = None  # for sub-registration forms


class RegistrationItemResponse(BaseModel):
    id: int
    sub_registration_id: int
    quantity: int
    unit_price: Decimal

    model_config = {"from_attributes": True}


class RegistrationResponse(BaseModel):
    id: int
    activity_id: int
    person_id: Optional[int] = None
    is_waitlist: bool
    registered_at: datetime
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    contact_phone: Optional[str] = None
    team_name: Optional[str] = None
    group_size: Optional[int] = None
    age_categories: Optional[str] = None
    remarks: Optional[str] = None
    payment_method: Optional[str] = None
    payment_status: Optional[str] = None
    items: List[RegistrationItemResponse] = []

    model_config = {"from_attributes": True}


class PublicRegistrationSummary(BaseModel):
    names: List[str]
    total_registrations: int
    total_participants: int
