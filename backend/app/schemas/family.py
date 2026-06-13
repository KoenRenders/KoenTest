from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, EmailStr, model_validator

class FamilyMemberCreate(BaseModel):
    last_name: str
    first_name: str
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    relation_type: str = "HOOFDLID"


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

    @model_validator(mode="after")
    def _hoofdlid_contactgegevens_verplicht(self):
        hoofdlid = next((m for m in self.members if m.relation_type == "HOOFDLID"), None)
        if hoofdlid is None:
            raise ValueError("Minstens één gezinslid moet het type 'HOOFDLID' hebben.")
        if not hoofdlid.email:
            raise ValueError("E-mailadres is verplicht voor het hoofdgezinslid.")
        if not hoofdlid.mobile:
            raise ValueError("Mobiel nummer is verplicht voor het hoofdgezinslid.")
        return self


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
    valid_from: Optional[date] = None
    valid_to: Optional[date] = None
    created_at: datetime

    model_config = {"from_attributes": True}
