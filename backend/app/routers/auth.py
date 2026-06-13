import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_admin, require_member, MEMBER_SCOPE
from app.database import get_db
from app.models.user import User
from app.models.login_token import LoginToken
from app.models.contact import ContactDetail
from app.schemas.auth import MagicLinkRequest, TokenResponse, UserResponse, MemberMeResponse
from app.services.email import send_magic_link, send_member_contact_board_notice
from app.services.member_auth import find_persons_by_email, resolve_household
from app.config import settings
from app.limiter import login_limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

MAGIC_LINK_EXPIRE_MINUTES = 15


@router.post("/auth/request-login", status_code=200, dependencies=[Depends(login_limiter)])
def request_login(body: MagicLinkRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email, User.is_active == True).first()
    if not user:
        return {"detail": "Als dit e-mailadres gekend is, ontvang je een inloglink."}

    token = secrets.token_urlsafe(64)
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=MAGIC_LINK_EXPIRE_MINUTES)
    login_token = LoginToken(user_id=user.id, token=token, expires_at=expires_at)
    db.add(login_token)
    db.commit()

    magic_link = f"{settings.frontend_url}/admin/login/verify?token={token}"

    if settings.debug:
        logger.warning("[DEBUG] Magic link for %s: %s", user.email, magic_link)

    send_magic_link(to_email=user.email, magic_link=magic_link)

    return {"detail": "Als dit e-mailadres gekend is, ontvang je een inloglink."}


@router.get("/auth/verify-login", response_model=TokenResponse)
def verify_login(token: str, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    login_token = (
        db.query(LoginToken)
        .filter(LoginToken.token == token, LoginToken.used == False, LoginToken.user_id.isnot(None))
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


# ---------------------------------------------------------------------------
# Lid-login (geen admin) — zelfde magic-link-mechanisme, aparte scope.
# ---------------------------------------------------------------------------
@router.post("/auth/member/request-login", status_code=200, dependencies=[Depends(login_limiter)])
def member_request_login(body: MagicLinkRequest, db: Session = Depends(get_db)):
    persons = find_persons_by_email(db, body.email)
    status_code, _member_id = resolve_household(db, persons)

    if status_code == "ok":
        token = secrets.token_urlsafe(64)
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=MAGIC_LINK_EXPIRE_MINUTES)
        db.add(LoginToken(email=body.email, token=token, expires_at=expires_at))
        db.commit()
        magic_link = f"{settings.frontend_url}/leden/login/verify?token={token}"
        if settings.debug:
            logger.warning("[DEBUG] Lid-magic-link voor %s: %s", body.email, magic_link)
        send_magic_link(to_email=body.email, magic_link=magic_link)
    elif status_code == "multiple":
        # E-mailadres hangt aan meerdere gezinnen: geen link, wel uitleg per mail.
        send_member_contact_board_notice(to_email=body.email)

    # Altijd dezelfde generieke respons — verklap niet of het adres gekend is.
    return {"detail": "Als dit e-mailadres gekend is, ontvang je een inloglink."}


@router.get("/auth/member/verify-login", response_model=TokenResponse)
def member_verify_login(token: str, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    login_token = (
        db.query(LoginToken)
        .filter(LoginToken.token == token, LoginToken.used == False, LoginToken.email.isnot(None))
        .first()
    )
    if not login_token or login_token.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ongeldige of verlopen inloglink.")

    login_token.used = True
    db.commit()

    access_token = create_access_token(data={"sub": login_token.email, "scope": MEMBER_SCOPE})
    return TokenResponse(access_token=access_token)


@router.get("/auth/member/me", response_model=MemberMeResponse)
def member_me(person=Depends(require_member), db: Session = Depends(get_db)):
    member_id = next((mp.member_id for mp in person.member_persons), None)
    email = next(
        (c.value for c in person.contact_details if c.contact_type_code == "EMAIL"), ""
    )
    phone = next(
        (c.value for c in person.contact_details
         if c.contact_type_code in ("MOBILE", "PHONE")),
        None,
    )
    return MemberMeResponse(
        person_id=person.id,
        member_id=member_id,
        name=f"{person.first_name} {person.last_name}".strip(),
        email=email,
        phone=phone,
    )
