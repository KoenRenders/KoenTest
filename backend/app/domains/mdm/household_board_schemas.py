"""What the Leden screen sends for the board's writes on a household (CR-13 phase 4c,
#1251): the request schemas of `household_board_service.py`. They describe mdm's
rows and moved here with the functions that write them; the answer schemas of the
screen's read model stay with membership."""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import BaseModel, EmailStr

from app.domains.mdm.models import RelationType


class PersonUpdate(BaseModel):
    last_name: Optional[str] = None
    first_name: Optional[str] = None
    date_of_birth: Optional[date] = None
    gender_code: Optional[str] = None


class AddressUpdate(BaseModel):
    street: Optional[str] = None
    house_number: Optional[str] = None
    bus_number: Optional[str] = None
    postal_code: Optional[str] = None


class ContactsUpdate(BaseModel):
    # #1831: an address has the shape of an address — the schema's question, as
    # for the household that signs up (`FamilyMemberCreate.email`).
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None


class PersonAddToFamily(BaseModel):
    last_name: str
    first_name: str
    date_of_birth: Optional[date] = None
    gender_code: Optional[str] = None
    email: Optional[EmailStr] = None
    phone: Optional[str] = None
    mobile: Optional[str] = None
    relation_type: RelationType = RelationType.PARTNER


class RelationChoice(BaseModel):
    """The relation a person's card asks for: one of the list (#1831)."""

    relation_type: RelationType


class BoardMemberAssign(BaseModel):
    person_id: Optional[int] = None
