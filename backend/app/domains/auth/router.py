import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.domains.auth.service import (
    create_access_token,
    get_current_identity,
    get_user_roles,
    require_member,
)
from app.database import get_db
from app.domains.auth.models import User
from app.domains.auth.models import LoginToken
from app.schemas.auth import (
    MagicLinkRequest,
    OtpVerifyRequest,
    TokenResponse,
    AuthMeResponse,
    MemberMeResponse,
)
from app.domains.mail.api import send_magic_link, send_member_contact_board_notice
from app.domains.auth.member_identity import (
    find_persons_by_email,
    resolve_household,
    login_person_for_email,
)
from app.config import settings
from app.limiter import login_limiter
from app.domains.auth.session import set_session_cookie as _set_ui_session_cookie


def _set_ui_session(response: Response, email: str) -> None:
    """Naast het JWT ook een HttpOnly-sessiecookie (#398): de server-rendered
    schermen (werkbank e.v.) lezen díe — nooit localStorage."""
    _set_ui_session_cookie(response, email)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["auth"])

# Gebruikersbeheer (backoffice-accounts + rollen) hoort bij het auth-component;
# de composer mount enkel deze router.
from app.domains.auth.users import router as _users_router  # noqa: E402
from app.i18n import _

router.include_router(_users_router)

# Eén bron voor de OTP-regels: ze horen bij de aanmeldstap (auth/login.py) en
# worden hier alleen hergebruikt, zodat router en scherm dezelfde grenzen hanteren.
from app.domains.auth.login import (  # noqa: E402,F401
    MAGIC_LINK_EXPIRE_MINUTES,
    MAX_OTP_ATTEMPTS,
    _generate_otp,
    _hash_otp,
    check_otp,
    start_login,
)



# ── Eén login-flow voor iedereen ───────────────────────────────────────────────
#
# Eén e-mailgebaseerde magic-link + OTP voor zowel backoffice-gebruikers als
# leden. "Gekend" = ofwel een actief user-account (backoffice), ofwel het
# e-mailadres hangt aan een Person (lid). Capabilities worden pas na login,
# per request, afgeleid — hier sturen we enkel een link/code naar wie gekend is.




@router.post("/auth/request-login", status_code=200, dependencies=[Depends(login_limiter)])
def request_login(body: MagicLinkRequest, db: Session = Depends(get_db)):
    start_login(db, body.email.strip())
    # Altijd dezelfde generieke respons — verklap niet of het adres gekend is.
    return {"detail": "Als dit e-mailadres gekend is, ontvang je een inloglink."}


@router.get("/auth/verify-login", response_model=TokenResponse)
def verify_login(token: str, response: Response, db: Session = Depends(get_db)):
    now = datetime.now(timezone.utc)
    login_token = (
        db.query(LoginToken)
        .filter(LoginToken.token == token, LoginToken.used == False, LoginToken.email.isnot(None))
        .first()
    )
    if not login_token or login_token.expires_at.replace(tzinfo=timezone.utc) < now:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=_("Ongeldige of verlopen inloglink."))

    login_token.used = True
    db.commit()
    _set_ui_session(response, login_token.email)
    return TokenResponse(access_token=create_access_token(data={"sub": login_token.email}))




@router.post("/auth/verify-otp", response_model=TokenResponse, dependencies=[Depends(login_limiter)])
def verify_otp(body: OtpVerifyRequest, response: Response, db: Session = Depends(get_db)):
    email = body.email.strip()
    if not check_otp(db, email, body.code):
        # Generieke melding: lek geen onderscheid tussen "geen token", "code fout"
        # en "te veel pogingen" — geen bruikbare feedback voor brute-force (#268).
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail=_("Ongeldige of verlopen code.")
        )
    _set_ui_session(response, email)
    return TokenResponse(access_token=create_access_token(data={"sub": email}))


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
    from app.domains.membership.api import renewal_available as _renewal_available
    from app.domains.membership.api import valid_membership_until

    valid_until = valid_membership_until(person)
    # Hernieuwingsvenster-regel op één plek (§19.3): membership-facade.
    renewal_available = _renewal_available(valid_until)

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


# ── API-keys voor machine-consumenten (§19.3) ──────────────────────────────────
#
# Beheer door een admin; de key zelf wordt exact één keer teruggegeven bij het
# aanmaken en daarna alleen gehasht bewaard.

from pydantic import BaseModel  # noqa: E402

from app.domains.auth.models import ApiKey  # noqa: E402
from app.domains.auth.service import get_current_admin, hash_api_key  # noqa: E402


class ApiKeyCreate(BaseModel):
    name: str


class ApiKeyOut(BaseModel):
    id: int
    name: str
    is_active: bool
    last_used_at: datetime | None = None
    model_config = {"from_attributes": True}


@router.get("/auth/api-keys", response_model=list[ApiKeyOut])
def list_api_keys(db: Session = Depends(get_db), _=Depends(get_current_admin)):
    return db.query(ApiKey).order_by(ApiKey.name).all()


@router.post("/auth/api-keys", status_code=201)
def create_api_key(body: ApiKeyCreate, db: Session = Depends(get_db),
                   _=Depends(get_current_admin)):
    name = body.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail=_("Naam is verplicht."))
    if db.query(ApiKey).filter(ApiKey.name == name).first():
        raise HTTPException(status_code=400, detail=_("Naam is al in gebruik."))
    plaintext = secrets.token_urlsafe(32)
    entry = ApiKey(name=name, key_hash=hash_api_key(plaintext))
    db.add(entry)
    db.commit()
    db.refresh(entry)
    # De key zelf is alléén nu zichtbaar — hij wordt enkel gehasht bewaard.
    return {"id": entry.id, "name": entry.name, "api_key": plaintext}


@router.delete("/auth/api-keys/{key_id}", status_code=204)
def revoke_api_key(key_id: int, db: Session = Depends(get_db),
                   _=Depends(get_current_admin)):
    entry = db.query(ApiKey).filter(ApiKey.id == key_id).first()
    if entry is None:
        raise HTTPException(status_code=404, detail=_("API-key niet gevonden."))
    entry.is_active = False
    db.commit()
