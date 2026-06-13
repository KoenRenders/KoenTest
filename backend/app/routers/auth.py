import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import create_access_token, get_current_admin, require_member, MEMBER_SCOPE
from app.database import get_db
from app.models.user import User, UserRole
from app.models.login_token import LoginToken
from app.models.contact import ContactDetail
from app.schemas.auth import MagicLinkRequest, OtpVerifyRequest, TokenResponse, UserResponse, MemberMeResponse
from app.services.email import send_magic_link, send_member_contact_board_notice
from app.services.member_auth import find_persons_by_email, resolve_household
from app.config import settings
from app.limiter import login_limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

MAGIC_LINK_EXPIRE_MINUTES = 15


def _ensure_member_user(db: Session, email: str) -> None:
    """Maak een User aan met rol MEMBER als die nog niet bestaat voor dit e-mailadres."""
    user = db.query(User).filter(func.lower(User.email) == email.strip().lower()).first()
    if not user:
        user = User(email=email.strip().lower(), is_active=True)
        db.add(user)
        db.flush()
        db.add(UserRole(user_id=user.id, role_code="MEMBER"))


def _generate_otp() -> str:
    """6-cijferige numerieke code (met voorloopnullen)."""
    return str(secrets.randbelow(1_000_000)).zfill(6)


@router.post("/auth/request-login", status_code=200, dependencies=[Depends(login_limiter)])
def request_login(body: MagicLinkRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email, User.is_active == True).first()
    if not user:
        return {"detail": "Als dit e-mailadres gekend is, ontvang je een inloglink."}

    token = secrets.token_urlsafe(64)
    otp_code = _generate_otp()
    expires_at = datetime.now(timezone.utc) + timedelta(minutes=MAGIC_LINK_EXPIRE_MINUTES)
    login_token = LoginToken(user_id=user.id, token=token, otp_code=otp_code, expires_at=expires_at)
    db.add(login_token)
    db.commit()

    magic_link = f"{settings.frontend_url}/admin/login/verify?token={token}"

    if settings.debug:
        logger.warning("[DEBUG] Magic link for %s: %s", user.email, magic_link)

    send_magic_link(to_email=user.email, magic_link=magic_link, otp_code=otp_code)

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


@router.post("/auth/verify-otp", response_model=TokenResponse, dependencies=[Depends(login_limiter)])
def verify_otp(body: OtpVerifyRequest, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    login_token = (
        db.query(LoginToken)
        .join(User, User.id == LoginToken.user_id)
        .filter(
            User.email == body.email,
            User.is_active == True,
            LoginToken.otp_code == body.code,
            LoginToken.used == False,
        )
        .order_by(LoginToken.id.desc())
        .first()
    )
    if not login_token or login_token.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ongeldige of verlopen code.")

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
        otp_code = _generate_otp()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=MAGIC_LINK_EXPIRE_MINUTES)
        db.add(LoginToken(email=body.email, token=token, otp_code=otp_code, expires_at=expires_at))
        db.commit()
        magic_link = f"{settings.frontend_url}/leden/login/verify?token={token}"
        if settings.debug:
            logger.warning("[DEBUG] Lid-magic-link voor %s: %s", body.email, magic_link)
        send_magic_link(to_email=body.email, magic_link=magic_link, otp_code=otp_code)
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
    _ensure_member_user(db, login_token.email)
    db.commit()

    access_token = create_access_token(data={"sub": login_token.email, "scope": MEMBER_SCOPE})
    return TokenResponse(access_token=access_token)


@router.post("/auth/member/verify-otp", response_model=TokenResponse, dependencies=[Depends(login_limiter)])
def member_verify_otp(body: OtpVerifyRequest, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    login_token = (
        db.query(LoginToken)
        .filter(
            func.lower(LoginToken.email) == body.email.strip().lower(),
            LoginToken.otp_code == body.code,
            LoginToken.used == False,
        )
        .order_by(LoginToken.id.desc())
        .first()
    )
    if not login_token or login_token.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Ongeldige of verlopen code.")

    login_token.used = True
    _ensure_member_user(db, login_token.email)
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
