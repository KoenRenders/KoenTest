from datetime import date, time as Time, datetime
from typing import Optional, List
from decimal import Decimal
from pydantic import BaseModel


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
    time: Optional[Time] = None
    location: Optional[str] = None
    max_participants: Optional[int] = None
    registration_type_code: Optional[str] = None
    price: Optional[Decimal] = None
    member_price: Optional[Decimal] = None
    poster_url: Optional[str] = None
    is_archived: Optional[bool] = None


class ActivityResponse(BaseModel):
    id: int
    name: str
    date: date
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

    model_config = {"from_attributes": True}


class RegistrationCreate(BaseModel):
    person_id: Optional[int] = None
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None
    registration_type: str = "INDIVIDUAL"


class RegistrationResponse(BaseModel):
    id: int
    activity_id: int
    person_id: Optional[int] = None
    is_waitlist: bool
    registered_at: datetime
    registration_type: str
    contact_name: Optional[str] = None
    contact_email: Optional[str] = None

    model_config = {"from_attributes": True}
