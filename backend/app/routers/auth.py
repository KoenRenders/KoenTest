import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.auth import (
    create_access_token,
    get_current_identity,
    get_user_roles,
    require_member,
)
from app.database import get_db
from app.models.user import User
from app.models.login_token import LoginToken
from app.schemas.auth import (
    MagicLinkRequest,
    OtpVerifyRequest,
    TokenResponse,
    AuthMeResponse,
    MemberMeResponse,
)
from app.services.email import send_magic_link, send_member_contact_board_notice
from app.services.member_auth import (
    find_persons_by_email,
    resolve_household,
    login_person_for_email,
)
from app.config import settings
from app.limiter import login_limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

MAGIC_LINK_EXPIRE_MINUTES = 15
# Brute-force-rem op de 6-cijferige OTP (#268): na zoveel foute codes op één
# token wordt het token geïnvalideerd en moet er een nieuwe code aangevraagd.
MAX_OTP_ATTEMPTS = 5


def _generate_otp() -> str:
    """6-cijferige numerieke code (met voorloopnullen)."""
    return str(secrets.randbelow(1_000_000)).zfill(6)

def _hash_otp(code: str) -> str:
    """OTP nooit leesbaar opslaan (#395): SHA-256 met SECRET_KEY als pepper.

    Een gelekte DB-dump geeft zo geen bruikbare codes; zonder pepper zou de
    10^6-ruimte offline triviaal te bruteforcen zijn.
    """
    return hashlib.sha256(f"{settings.secret_key}:{code}".encode()).hexdigest()



# ── Eén login-flow voor iedereen ───────────────────────────────────────────────
#
# Eén e-mailgebaseerde magic-link + OTP voor zowel backoffice-gebruikers als
# leden. "Gekend" = ofwel een actief user-account (backoffice), ofwel het
# e-mailadres hangt aan een Person (lid). Capabilities worden pas na login,
# per request, afgeleid — hier sturen we enkel een link/code naar wie gekend is.


@router.post("/auth/request-login", status_code=200, dependencies=[Depends(login_limiter)])
def request_login(body: MagicLinkRequest, db: Session = Depends(get_db)):
    email = body.email.strip()

    # Twee onafhankelijke checks: heeft dit adres een account, en/of hangt het
    # aan een persoon (en is dat gezin eenduidig)?
    user = (
        db.query(User)
        .filter(func.lower(User.email) == email.lower(), User.is_active == True)
        .first()
    )
    persons = find_persons_by_email(db, email)
    household_status, _member_id = resolve_household(db, persons)

    if user is not None or household_status == "ok":
        token = secrets.token_urlsafe(64)
        otp_code = _generate_otp()
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=MAGIC_LINK_EXPIRE_MINUTES)
        # Eén levende OTP per e-mail (#268): invalideer bestaande ongebruikte,
        # niet-verlopen tokens vóór we een nieuwe maken, zodat er hoogstens één
        # geldige code tegelijk leeft (verkleint de gok-kans).
        db.query(LoginToken).filter(
            func.lower(LoginToken.email) == email.lower(),
            LoginToken.used == False,
            LoginToken.expires_at > datetime.now(timezone.utc),
        ).update({LoginToken.used: True}, synchronize_session=False)
        db.add(LoginToken(email=email, token=token, otp_code=_hash_otp(otp_code), expires_at=expires_at))
        db.commit()
        magic_link = f"{settings.frontend_url}/login/verify?token={token}"
        if settings.debug:
            logger.warning("[DEBUG] Inloglink voor %s: %s", email, magic_link)
        send_magic_link(to_email=email, magic_link=magic_link, otp_code=otp_code)
    elif household_status == "multiple":
        # E-mailadres hangt aan meerdere gezinnen en is geen account: geen link,
        # wel uitleg per mail (we mogen niet gokken welk gezin bedoeld is).
        send_member_contact_board_notice(to_email=email)

    # Altijd dezelfde generieke respons — verklap niet of het adres gekend is.
    return {"detail": "Als dit e-mailadres gekend is, ontvang je een inloglink."}


@router.get("/auth/verify-login", response_model=TokenResponse)
def verify_login(token: str, db: Session = Depends(get_db)):
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
    return TokenResponse(access_token=create_access_token(data={"sub": login_token.email}))


@router.post("/auth/verify-otp", response_model=TokenResponse, dependencies=[Depends(login_limiter)])
def verify_otp(body: OtpVerifyRequest, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    # Haal het levende token voor dit e-mailadres (ongebruikt), ONAFHANKELIJK van
    # de ingevoerde code — zo kunnen we ook een foute poging tellen (#268). Door
    # 'één levende OTP per e-mail' is dit het enige relevante token.
    login_token = (
        db.query(LoginToken)
        .filter(
            func.lower(LoginToken.email) == body.email.strip().lower(),
            LoginToken.used == False,
        )
        .order_by(LoginToken.id.desc())
        .first()
    )
    # Generieke melding: lek geen onderscheid tussen "geen token", "code fout" en
    # "te veel pogingen" — geen bruikbare feedback voor een brute-force (#268).
    invalid = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Ongeldige of verlopen code."
    )
    if not login_token or login_token.expires_at.replace(tzinfo=timezone.utc) < now:
        raise invalid

    if login_token.otp_code != _hash_otp(body.code):
        # Foute code: tel de poging en maak het token dood na MAX_OTP_ATTEMPTS,
        # zodat de 10^6-ruimte niet uitputbaar is zodra de IP-limiet omzeild wordt.
        login_token.attempts += 1
        if login_token.attempts >= MAX_OTP_ATTEMPTS:
            login_token.used = True
        db.commit()
        raise invalid

    login_token.used = True
    db.commit()
    return TokenResponse(access_token=create_access_token(data={"sub": login_token.email}))


@router.get("/auth/me", response_model=AuthMeResponse)
def auth_me(email: str = Depends(get_current_identity), db: Session = Depends(get_db)):
    """Wie ben ik en wat mag ik — per request afgeleid uit de data."""
    roles = sorted(get_user_roles(db, email))
    person = login_person_for_email(db, email)
    return AuthMeResponse(
        email=email,
        roles=roles,
        is_admin="ADMIN" in roles,
        is_finance="FINANCE" in roles,
        is_member=person is not None,
        member_name=(f"{person.first_name} {person.last_name}".strip() if person else None),
    )


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
    from app.services.membership import valid_membership_until
    from datetime import date

    valid_until = valid_membership_until(person)
    today = date.today()
    renewal_open = False
    if settings.membership_renewal_start_md:
        try:
            month, day = (int(x) for x in settings.membership_renewal_start_md.split("-"))
            renewal_open = today >= date(today.year, month, day)
        except (ValueError, TypeError):
            pass
    renewal_available = (valid_until is None) or renewal_open

    return MemberMeResponse(
        person_id=person.id,
        member_id=member_id,
        name=f"{person.first_name} {person.last_name}".strip(),
        email=email,
        phone=phone,
        has_valid_membership=valid_until is not None,
        membership_valid_until=valid_until,
        renewal_available=renewal_available,
    )
