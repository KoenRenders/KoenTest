from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, EmailStr

RELATION_TYPES = ["hoofdlid", "partner", "(meerderjarig) kind"]


class FamilyMemberCreate(BaseModel):
    last_name: str
    first_name: str
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    relation_type: str = "hoofdlid"


class FamilyMemberUpdate(BaseModel):
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    relation_type: Optional[str] = None


class FamilyMemberResponse(BaseModel):
    id: int
    last_name: str
    first_name: str
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    relation_type: str

    model_config = {"from_attributes": True}


class FamilyCreate(BaseModel):
    street: str
    house_number: str
    bus_number: Optional[str] = None
    postal_code: str
    municipality: Optional[str] = None
    payment_method: str = "cash"  # "cash", "transfer", "online"
    members: List[FamilyMemberCreate] = []


class FamilyRegisteredResponse(BaseModel):
    id: int
    status: str
    checkout_url: Optional[str] = None
    amount: Optional[Decimal] = None


class MembershipCreate(BaseModel):
    year: int
    is_active: bool = True


class MembershipResponse(BaseModel):
    id: int
    member_id: int
    year: int
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
