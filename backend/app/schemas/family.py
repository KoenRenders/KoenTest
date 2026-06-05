from __future__ import annotations
from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr


class FamilyMemberCreate(BaseModel):
    last_name: str
    first_name: str
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    member_type: Optional[str] = None
    is_primary: bool = False


class FamilyMemberUpdate(BaseModel):
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_primary: Optional[bool] = None


class FamilyMemberResponse(BaseModel):
    id: int
    family_id: int
    last_name: str
    first_name: str
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    is_primary: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class FamilyCreate(BaseModel):
    street: str
    house_number: str
    bus_number: Optional[str] = None
    postal_code: str
    municipality: Optional[str] = None
    members: List[FamilyMemberCreate] = []


class FamilyUpdate(BaseModel):
    street: Optional[str] = None
    house_number: Optional[str] = None
    bus_number: Optional[str] = None
    postal_code: Optional[str] = None
    municipality: Optional[str] = None


class FamilyResponse(BaseModel):
    id: int
    street: str
    house_number: str
    bus_number: Optional[str] = None
    postal_code: str
    municipality: str
    created_at: datetime
    members: List[FamilyMemberResponse] = []

    model_config = {"from_attributes": True}


class MembershipCreate(BaseModel):
    year: int
    is_active: bool = True


class MembershipResponse(BaseModel):
    id: int
    family_id: int
    year: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
