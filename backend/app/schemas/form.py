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


class FormFieldIn(BaseModel):
    field_type: str
    label: str
    help_text: Optional[str] = None
    required: bool = False
    position: int = 0
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
    fields: List[FormFieldIn] = []


class FormUpdate(FormCreate):
    pass


# ── Admin: lezen ────────────────────────────────────────────────────────────────

class FormFieldOptionOut(BaseModel):
    id: int
    label: str
    value: Optional[str] = None
    position: int

    model_config = {"from_attributes": True}


class FormFieldOut(BaseModel):
    id: int
    field_type: str
    label: str
    help_text: Optional[str] = None
    required: bool
    position: int
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
    created_at: datetime
    updated_at: datetime
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

    model_config = {"from_attributes": True}


class PublicField(BaseModel):
    id: int
    field_type: str
    label: str
    help_text: Optional[str] = None
    required: bool
    position: int
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
    fields: List[PublicField] = []

    model_config = {"from_attributes": True}


class AnswerIn(BaseModel):
    field_id: int
    text: Optional[str] = None
    number: Optional[Decimal] = None
    # Eén optie (radio/select) of meerdere (checkbox).
    option_ids: List[int] = []
    rating: Optional[int] = None


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


class EditSubmissionOut(BaseModel):
    form: PublicForm
    submitter_name: Optional[str] = None
    submitter_email: Optional[str] = None
    answers: List[SubmissionAnswerOut] = []
