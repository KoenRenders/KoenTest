import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_admin
from app.database import get_db
from app.models.user import User
from app.models.login_token import LoginToken
from app.schemas.auth import MagicLinkRequest, TokenResponse, UserResponse
from app.services.email import send_magic_link
from app.config import settings

router = APIRouter(tags=["auth"])

MAGIC_LINK_EXPIRE_MINUTES = 15


@router.post("/auth/request-login", status_code=200)
def request_login(body: MagicLinkRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email, User.is_active == True).first()
    if not user:
        # Geef geen foutmelding terug — security by obscurity
        return {"detail": "Als dit e-mailadres gekend is, ontvang je een inloglink."}

    token = secrets.token_urlsafe(64)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=MAGIC_LINK_EXPIRE_MINUTES)
    login_token = LoginToken(user_id=user.id, token=token, expires_at=expires_at)
    db.add(login_token)
    db.commit()

    magic_link = f"{settings.frontend_url}/admin/login/verify?token={token}"
    send_magic_link(to_email=user.email, magic_link=magic_link)

    return {"detail": "Als dit e-mailadres gekend is, ontvang je een inloglink."}


@router.get("/auth/verify-login", response_model=TokenResponse)
def verify_login(token: str, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    login_token = (
        db.query(LoginToken)
        .filter(LoginToken.token == token, LoginToken.used == False)
        .first()
    )
    if not login_token or login_token.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ongeldige of verlopen inloglink.")

    login_token.used = True
    db.commit()

    access_token = create_access_token(data={"sub": login_token.user.email})
    return TokenResponse(access_token=access_token)


@router.get("/auth/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_admin)):
    return current_user
