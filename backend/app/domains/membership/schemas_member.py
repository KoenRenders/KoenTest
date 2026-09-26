"""Pydantic-schemas voor leden/gezinnen (verhuisd uit app/schemas/member.py, #444)."""
from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel
from app.domains.mdm.api import RelationType


class PersonCreate(BaseModel):
    last_name: str
    first_name: str
    date_of_birth: Optional[date] = None
    gender_code: Optional[str] = None
    gender: Optional[str] = None  # alias used by public registration form
    is_primary: bool = False
    # CR-12 phase 2: form → router (Pydantic). An unknown relation type is
    # now a 422 naming the field, instead of a row that only trips over the
    # foreign key.
    relation_type: RelationType = RelationType.PRIMARY_MEMBER


class PersonUpdate(BaseModel):
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender_code: Optional[str] = None


class PersonResponse(BaseModel):
    id: int
    last_name: str
    first_name: str
    date_of_birth: Optional[date] = None
    gender_code: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class MemberCreate(BaseModel):
    persons: List[PersonCreate] = []


class MemberResponse(BaseModel):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


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
    updated_at: datetime

    model_config = {"from_attributes": True}


class FamilyMemberResponse(BaseModel):
    id: int
    last_name: str
    first_name: str
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    relation_type: RelationType


class PersonListItem(BaseModel):
    id: int
    last_name: str
    first_name: str

    model_config = {"from_attributes": True}


class FamilyResponse(BaseModel):
    id: int
    street: str
    house_number: str
    bus_number: Optional[str] = None
    postal_code: str
    municipality: str
    members: List[FamilyMemberResponse]
    memberships: List[MembershipResponse] = []
    board_member: Optional[PersonListItem] = None

    @property
    def primary(self) -> Optional[FamilyMemberResponse]:
        """The primary member (hoofdlid) of this household, or None.

        CR-12 §B4.7: this used to be
        `selectattr("relation_type", "equalto", "HOOFDLID")` in the member list.
        With a plain `Enum` on that column such a comparison is silently false
        and the screen falls back to "the first person" — without anything
        complaining. Who the primary member is, is a rule; it belongs here and
        not in Jinja.
        """
        return next((m for m in self.members
                     if m.relation_type is RelationType.PRIMARY_MEMBER), None)


class AddressUpdate(BaseModel):
    street: Optional[str] = None
    house_number: Optional[str] = None
    bus_number: Optional[str] = None
    postal_code: Optional[str] = None


class ContactsUpdate(BaseModel):
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None


class PersonAddToFamily(BaseModel):
    last_name: str
    first_name: str
    date_of_birth: Optional[date] = None
    gender_code: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    relation_type: RelationType = RelationType.PARTNER


class BoardMemberAssign(BaseModel):
    person_id: Optional[int] = None


class FamilyRegisteredResponse(BaseModel):
    id: int
    status: str
    checkout_url: Optional[str] = None
    amount: Optional[Decimal] = None


class PostalCodeResponse(BaseModel):
    postal_code: str
    municipality: str


class PaginatedFamiliesResponse(BaseModel):
    items: List[FamilyResponse]
    total: int
    page: int
    page_size: int
    total_pages: int


class PaginatedMembersResponse(BaseModel):
    items: List[MemberResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
