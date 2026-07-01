from __future__ import annotations
from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from pydantic import BaseModel


# ── Admin: schrijven ────────────────────────────────────────────────────────────

class FormFieldOptionIn(BaseModel):
    label: str
    value: Optional[str] = None
    position: int = 0
    is_other: bool = False
    # Branching (#336): verwijst naar de index in de `sections`-lijst van de payload.
    skip_to_section_index: Optional[int] = None
    skip_to_end: bool = False


class FormSectionIn(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    position: int = 0
    # Sectie-navigatie (#336): index in de `sections`-lijst waar na deze sectie
    # naartoe gesprongen wordt (None + next_is_end=false = lineair).
    next_section_index: Optional[int] = None
    next_is_end: bool = False


class FormFieldIn(BaseModel):
    field_type: str
    label: str
    help_text: Optional[str] = None
    required: bool = False
    position: int = 0
    # Verwijst naar de index in de `sections`-lijst van de payload (None = ongegroepeerd).
    section_index: Optional[int] = None
    min_value: Optional[Decimal] = None
    max_value: Optional[Decimal] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    regex_pattern: Optional[str] = None
    options: List[FormFieldOptionIn] = []


class FormCreate(BaseModel):
    title: str
    slug: Optional[str] = None
    description: Optional[str] = None
    status: str = "draft"
    requires_login: bool = False
    max_submissions: Optional[int] = None
    send_confirmation: bool = False
    confirmation_message: Optional[str] = None
    allow_edit: bool = False
    is_anonymous: bool = False
    sections: List[FormSectionIn] = []
    fields: List[FormFieldIn] = []


class FormUpdate(FormCreate):
    pass


# ── Admin: lezen ────────────────────────────────────────────────────────────────

class FormFieldOptionOut(BaseModel):
    id: int
    label: str
    value: Optional[str] = None
    position: int
    is_other: bool = False
    skip_to_section_id: Optional[int] = None
    skip_to_end: bool = False

    model_config = {"from_attributes": True}


class FormSectionOut(BaseModel):
    id: int
    title: Optional[str] = None
    description: Optional[str] = None
    position: int
    next_section_id: Optional[int] = None
    next_is_end: bool = False

    model_config = {"from_attributes": True}


class FormFieldOut(BaseModel):
    id: int
    field_type: str
    label: str
    help_text: Optional[str] = None
    required: bool
    position: int
    section_id: Optional[int] = None
    min_value: Optional[Decimal] = None
    max_value: Optional[Decimal] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    regex_pattern: Optional[str] = None
    options: List[FormFieldOptionOut] = []

    model_config = {"from_attributes": True}


class FormAdminOut(BaseModel):
    id: int
    title: str
    slug: Optional[str] = None
    description: Optional[str] = None
    share_token: str
    status: str
    requires_login: bool
    max_submissions: Optional[int] = None
    send_confirmation: bool
    confirmation_message: Optional[str] = None
    allow_edit: bool
    is_anonymous: bool = False
    created_at: datetime
    updated_at: datetime
    sections: List[FormSectionOut] = []
    fields: List[FormFieldOut] = []
    submission_count: int = 0

    model_config = {"from_attributes": True}


class FormSummary(BaseModel):
    id: int
    title: str
    status: str
    share_token: str
    submission_count: int = 0
    created_at: datetime

    model_config = {"from_attributes": True}


# ── Publiek: lezen + indienen ───────────────────────────────────────────────────

class PublicFieldOption(BaseModel):
    id: int
    label: str
    value: Optional[str] = None
    is_other: bool = False
    skip_to_section_id: Optional[int] = None
    skip_to_end: bool = False

    model_config = {"from_attributes": True}


class PublicSection(BaseModel):
    id: int
    title: Optional[str] = None
    description: Optional[str] = None
    position: int
    next_section_id: Optional[int] = None
    next_is_end: bool = False

    model_config = {"from_attributes": True}


class PublicField(BaseModel):
    id: int
    field_type: str
    label: str
    help_text: Optional[str] = None
    required: bool
    position: int
    section_id: Optional[int] = None
    min_value: Optional[Decimal] = None
    max_value: Optional[Decimal] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    options: List[PublicFieldOption] = []

    model_config = {"from_attributes": True}


class PublicForm(BaseModel):
    id: int
    title: str
    description: Optional[str] = None
    status: str
    allow_edit: bool
    send_confirmation: bool = False
    is_anonymous: bool = False
    sections: List[PublicSection] = []
    fields: List[PublicField] = []

    model_config = {"from_attributes": True}


class AnswerIn(BaseModel):
    field_id: int
    text: Optional[str] = None
    number: Optional[Decimal] = None
    # Eén optie (radio/select) of meerdere (checkbox).
    option_ids: List[int] = []
    rating: Optional[int] = None
    # Vrije tekst bij een aangevinkte "Andere…"-optie (#337).
    other_text: Optional[str] = None


class SubmissionIn(BaseModel):
    submitter_name: Optional[str] = None
    submitter_email: Optional[str] = None
    answers: List[AnswerIn] = []


class SubmissionResult(BaseModel):
    id: int
    status: str
    edit_token: Optional[str] = None


# ── Wijzig-flow (lezen via edit_token) ──────────────────────────────────────────

class SubmissionAnswerOut(BaseModel):
    field_id: int
    text: Optional[str] = None
    number: Optional[Decimal] = None
    option_ids: List[int] = []
    rating: Optional[int] = None
    other_text: Optional[str] = None


class EditSubmissionOut(BaseModel):
    form: PublicForm
    submitter_name: Optional[str] = None
    submitter_email: Optional[str] = None
    answers: List[SubmissionAnswerOut] = []
