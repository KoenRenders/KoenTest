from __future__ import annotations
from typing import Optional
from pydantic import BaseModel


class MagicLinkRequest(BaseModel):
    email: str


class OtpVerifyRequest(BaseModel):
    email: str
    code: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    is_active: bool

    model_config = {"from_attributes": True}


AdminUserResponse = UserResponse


class MemberMeResponse(BaseModel):
    person_id: int
    member_id: int
    name: str
    email: str
    phone: Optional[str] = None
