from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import verify_password, create_access_token, get_current_admin
from app.database import get_db
from app.models.user import AdminUser
from app.schemas.auth import LoginRequest, TokenResponse, AdminUserResponse
from app.config import settings

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=TokenResponse)
def login(request: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(AdminUser).filter(AdminUser.username == request.username).first()
    if not user or not verify_password(request.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
        )
    access_token = create_access_token(
        data={"sub": user.username},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return TokenResponse(access_token=access_token)


@router.get("/auth/me", response_model=AdminUserResponse)
def get_me(current_admin: AdminUser = Depends(get_current_admin)):
    return current_admin
