from __future__ import annotations
from pydantic import BaseModel


class MagicLinkRequest(BaseModel):
    email: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: int
    email: str
    is_active: bool

    model_config = {"from_attributes": True}


AdminUserResponse = UserResponse
