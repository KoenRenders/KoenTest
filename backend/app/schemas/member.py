from datetime import date, datetime
from typing import Optional, List
from pydantic import BaseModel


class PersonCreate(BaseModel):
    last_name: str
    first_name: str
    date_of_birth: Optional[date] = None
    gender_code: Optional[str] = None
    is_primary: bool = False


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


class AddressCreate(BaseModel):
    street: str
    house_number: str
    bus_number: Optional[str] = None
    postal_code_id: int


class AddressResponse(BaseModel):
    id: int
    person_id: int
    street: str
    house_number: str
    bus_number: Optional[str] = None
    postal_code_id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ContactDetailCreate(BaseModel):
    contact_type_code: str
    value: str
    is_primary: bool = False


class ContactDetailResponse(BaseModel):
    id: int
    person_id: int
    contact_type_code: str
    value: str
    is_primary: bool
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
    is_primary: bool


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
    is_primary: bool = False


class BoardMemberAssign(BaseModel):
    person_id: Optional[int] = None


class FamilyRegisteredResponse(BaseModel):
    id: int
    status: str


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
