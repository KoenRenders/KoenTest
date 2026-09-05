"""De aanmeldstap: magic link en OTP (#635 I).

`start_login` en `check_otp` stonden in `auth/router.py` — geen routes, gewone
functies, maar wél in het bestand dat de JSON-API definieert. Het aanmeldscherm
importeerde ze daar rechtstreeks, en dat is wat #635 punt 3 beschrijft: de router
als servicelaag. Ze dragen de regels die tellen — een onbekend adres krijgt géén
signaal, een adres bij meerdere gezinnen krijgt uitleg in plaats van een link, en
de pogingteller met lockout (#268) — dus ze horen in de service.
"""
import logging
import secrets
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.domains.auth.member_identity import find_persons_by_email, resolve_household
from app.domains.auth.models import LoginToken, User
import hashlib

MAGIC_LINK_EXPIRE_MINUTES = 15
# Brute-force-rem op de 6-cijferige OTP (#268): na zoveel foute codes op één token
# wordt het token geïnvalideerd en moet er een nieuwe code aangevraagd worden.
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
from app.domains.mail.api import send_magic_link, send_member_contact_board_notice

logger = logging.getLogger(__name__)


def start_login(db: Session, email: str) -> None:
    """De volledige request-login-stap (ook gebruikt door het aanmeldscherm,
    fase 1 #399): gekend adres → magic-link + OTP; meerdere gezinnen → uitleg-
    mail; onbekend → stil. De aanroeper toont ALTIJD dezelfde generieke respons."""
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
        from app.kernel.tenant_config import tenant_base_url

        magic_link = f"{tenant_base_url(db)}/login/verify?token={token}"
        if settings.debug:
            logger.warning("[DEBUG] Inloglink voor %s: %s", email, magic_link)
        send_magic_link(to_email=email, magic_link=magic_link, otp_code=otp_code)
    elif household_status == "multiple":
        # E-mailadres hangt aan meerdere gezinnen en is geen account: geen link,
        # wel uitleg per mail (we mogen niet gokken welk gezin bedoeld is).
        send_member_contact_board_notice(to_email=email)


def check_otp(db: Session, email: str, code: str) -> bool:
    """De volledige OTP-controle (ook gebruikt door het aanmeldscherm, fase 1
    #399), inclusief pogingteller en lockout (#268). True = code klopt en het
    token is verbruikt; False = generiek ongeldig (geen detail-onderscheid)."""
    now = datetime.now(timezone.utc)
    # Haal het levende token voor dit e-mailadres (ongebruikt), ONAFHANKELIJK van
    # de ingevoerde code — zo kunnen we ook een foute poging tellen (#268). Door
    # 'één levende OTP per e-mail' is dit het enige relevante token.
    login_token = (
        db.query(LoginToken)
        .filter(
            func.lower(LoginToken.email) == email.strip().lower(),
            LoginToken.used == False,
        )
        .order_by(LoginToken.id.desc())
        .first()
    )
    if not login_token or login_token.expires_at.replace(tzinfo=timezone.utc) < now:
        return False

    if login_token.otp_code != _hash_otp(code):
        # Foute code: tel de poging en maak het token dood na MAX_OTP_ATTEMPTS,
        # zodat de 10^6-ruimte niet uitputbaar is zodra de IP-limiet omzeild wordt.
        login_token.attempts += 1
        if login_token.attempts >= MAX_OTP_ATTEMPTS:
            login_token.used = True
        db.commit()
        return False

    login_token.used = True
    db.commit()
    return True
