from __future__ import annotations
from typing import List, Optional
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


class AuthMeResponse(BaseModel):
    """Wie ben ik en wat mag ik — capabilities per request afgeleid.

    `roles` = backoffice-rollen (users/user_roles, bv. ADMIN). `is_member`/
    `member_name` komen uit het leden-domein (e-mail -> Person), volledig los
    van het rollensysteem.
    """
    email: str
    roles: List[str] = []
    is_admin: bool = False
    is_member: bool = False
    member_name: Optional[str] = None


class MemberMeResponse(BaseModel):
    person_id: int
    member_id: int
    name: str
    email: str
    phone: Optional[str] = None
