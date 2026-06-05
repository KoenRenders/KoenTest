from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.auth import verify_password, create_access_token, get_current_admin
from app.database import get_db
from app.main import limiter
from app.models.user import User
from app.schemas.auth import LoginRequest, TokenResponse, UserResponse
from app.config import settings

router = APIRouter(tags=["auth"])


@router.post("/auth/login", response_model=TokenResponse)
@limiter.limit("10/minute")
def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email, User.is_active == True).first()
    if not user or not verify_password(body.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
        )
    access_token = create_access_token(
        data={"sub": user.email},
        expires_delta=timedelta(minutes=settings.access_token_expire_minutes),
    )
    return TokenResponse(access_token=access_token)


@router.get("/auth/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_admin)):
    return current_user
