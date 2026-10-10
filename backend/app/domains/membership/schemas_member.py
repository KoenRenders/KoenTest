"""Pydantic-schemas voor leden/gezinnen (verhuisd uit app/schemas/member.py, #444)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel

from app.domains.mdm.api import RelationType


class PersonResponse(BaseModel):
    id: int
    last_name: str
    first_name: str
    date_of_birth: Optional[date] = None
    gender_code: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


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


class EmailAddressResponse(BaseModel):
    """Eén e-mailadres van een persoon (#1174).

    Met het rij-id erbij, want het scherm moet er een kúnnen aanwijzen of
    verwijderen — en twee personen kunnen hetzelfde adres dragen, dus de waarde
    alleen is geen sleutel.
    """

    id: int
    value: str
    is_primary: bool
    #: CR-22 R15 (#1711, #1733): False while the address waits for its code —
    #: it does not sign in and cannot be the main address. The same field as
    #: on the member's side (`mdm.person_payload`).
    confirmed: bool = True

    @property
    def can_be_primary(self) -> bool:
        """Is "Maak hoofdadres" an action that can succeed on this row? Not on
        the main address itself, and not on one that waits (the rule refuses it,
        `mdm.service.make_email_primary`)."""
        return self.confirmed and not self.is_primary


class FamilyMemberResponse(BaseModel):
    id: int
    last_name: str
    first_name: str
    date_of_birth: Optional[date] = None
    gender: Optional[str] = None
    # Het HOOFDadres (#1174) — het adres dat Raak Nationaal kent. Eén veld, want
    # elk scherm dat "het e-mailadres" toont bedoelt dit; de rest staat in
    # `emails`.
    email: Optional[str] = None
    #: #1733: `email` is an address that still waits for its code — the person
    #: has none that counts.
    email_waiting: bool = False
    phone: Optional[str] = None
    mobile: Optional[str] = None
    relation_type: RelationType
    # Álle adressen, hoofdadres eerst en daarna op id (#1174). Het beheerscherm
    # beheert deze lijst; de nieuwsbrief verstuurt ernaar.
    emails: list[EmailAddressResponse] = []

    @property
    def is_main_member(self) -> bool:
        """Decided here and not in the template (CR-12 phase 4 residue): the
        template compared `relation_type` with "HOOFDLID", and a `RelationType`
        member never equals that string."""
        return self.relation_type is RelationType.PRIMARY_MEMBER


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
        return next(
            (m for m in self.members if m.relation_type is RelationType.PRIMARY_MEMBER), None
        )


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
