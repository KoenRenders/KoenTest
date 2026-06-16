from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
# Voor lid-endpoints: een ontbrekend token mag geen 401 geven (publieke
# registratie werkt ook zonder login), vandaar auto_error=False.
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.access_token_expire_minutes)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)
    return encoded_jwt


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )


def _email_from_token(token: str) -> str:
    """Het e-mailadres (`sub`) uit een geldig token, of 401."""
    payload = decode_token(token)
    email = payload.get("sub")
    if not email:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    return email


# ── Eén identiteit, capabilities per request afgeleid ──────────────────────────
#
# Het token bevat enkel de identiteit ({"sub": email}). Wat iemand mág wordt bij
# élke request opnieuw bepaald uit de data — nooit gebakken in het token. Zo
# verleent een token altijd exact wat de data op dat moment zegt (een ingetrokken
# rol of vervallen koppeling werkt meteen door) en blijven twee domeinen
# maximaal gescheiden:
#   - backoffice-rollen (ADMIN, later bv. FINANCE) leven in users/user_roles;
#   - lid-zijn is afgeleid uit ContactDetail (e-mail hangt aan een Person).
# De enige brug tussen beide domeinen is de e-mailwaarde, geen foreign key.


def get_user_roles(db: Session, email: str) -> set:
    """Backoffice-rollen voor dit e-mailadres. Leeg als er geen actief account is."""
    from app.models.user import User, UserRole

    rows = (
        db.query(UserRole.role_code)
        .join(User, User.id == UserRole.user_id)
        .filter(func.lower(User.email) == email.strip().lower(), User.is_active == True)
        .all()
    )
    return {r[0] for r in rows}


def get_current_identity(token: str = Depends(oauth2_scheme)) -> str:
    """Vereist enkel een geldig token; geeft het e-mailadres terug (geen rolcheck)."""
    return _email_from_token(token)


def require_roles(*codes: str):
    """Dependency-factory: vereist minstens één van de opgegeven backoffice-rollen.

    Generiek opgezet: een nieuwe rol (bv. FINANCE) aan een router hangen is
    `Depends(require_roles("ADMIN", "FINANCE"))` — zonder wijziging aan de
    auth-laag zelf. Geeft de bijbehorende User terug.
    """
    from app.models.user import User

    def _dep(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
        email = _email_from_token(token)
        roles = get_user_roles(db, email)
        if not roles.intersection(codes):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions",
            )
        user = (
            db.query(User)
            .filter(func.lower(User.email) == email.strip().lower(), User.is_active == True)
            .first()
        )
        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )
        return user

    return _dep


# Admin = backoffice-rol ADMIN. Dunne alias bovenop de generieke require_roles,
# zodat bestaande routers (Depends(get_current_admin)) ongemoeid blijven.
get_current_admin = require_roles("ADMIN")

# Financiële scheiding (penningmeester): enkel FINANCE mag betalingen invullen,
# bewerken, terugbetalen of verwijderen. ADMIN mag betalingen wél inkijken maar
# niet wijzigen → de view-endpoints aanvaarden beide rollen.
get_current_finance = require_roles("FINANCE")
get_finance_or_admin = require_roles("ADMIN", "FINANCE")


def get_current_member(
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
):
    """Optionele lid-identificatie. Geeft de ingelogde Person terug, of None.

    Geeft nooit 401: ontbreekt het token of leidt het e-mailadres niet naar een
    Person, dan is de aanvrager simpelweg anoniem (None). De koppeling
    e-mail -> Person gebeurt elke request opnieuw via het leden-domein
    (ContactDetail), volledig los van het users-domein. Een admin die met
    hetzelfde e-mailadres als zijn Person inlogt, is daardoor automatisch óók
    lid — zonder opgeslagen koppeling.
    """
    from app.services.member_auth import login_person_for_email

    if not token:
        return None
    try:
        payload = decode_token(token)
    except HTTPException:
        return None
    email = payload.get("sub")
    if not email:
        return None
    return login_person_for_email(db, email)


def require_member(member=Depends(get_current_member)):
    """Lid-endpoints die wél inloggen vereisen (bv. profiel, gezin)."""
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Niet ingelogd als lid.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return member
