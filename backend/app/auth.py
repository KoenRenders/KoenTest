from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
# Voor lid-endpoints: een ontbrekend token mag geen 401 geven (publieke
# registratie werkt ook zonder login), vandaar auto_error=False.
oauth2_scheme_optional = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)

MEMBER_SCOPE = "member"


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.access_token_expire_minutes)
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


def get_current_admin(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    from app.models.user import User, UserRole

    payload = decode_token(token)
    email: str = payload.get("sub")
    if email is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate credentials",
        )
    user = db.query(User).filter(User.email == email, User.is_active == True).first()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    has_admin_role = (
        db.query(UserRole)
        .filter(UserRole.user_id == user.id, UserRole.role_code == "ADMIN")
        .first()
    )
    if not has_admin_role:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )
    return user


def get_current_member(
    token: Optional[str] = Depends(oauth2_scheme_optional),
    db: Session = Depends(get_db),
):
    """Optionele lid-identificatie. Geeft de ingelogde Person terug, of None.

    Geeft nooit 401: ontbreekt het token of is het geen geldig lid-token, dan
    is de aanvrager simpelweg anoniem (None).

    Twee paden:
    - Lid-token (scope=member): e-mail → Person via ContactDetail.
    - Admin-token (geen scope): als de User een person_id heeft, wordt die
      Person teruggegeven — admins kunnen zo hun gezin beheren en zich
      inschrijven zonder aparte ledenlogin.
    """
    from app.services.member_auth import login_person_for_email
    from app.models.member import Person

    if not token:
        return None
    try:
        payload = decode_token(token)
    except HTTPException:
        return None

    if payload.get("scope") == MEMBER_SCOPE:
        email = payload.get("sub")
        if not email:
            return None
        return login_person_for_email(db, email)

    # Admin-token: gebruik person_id als die gekoppeld is
    email = payload.get("sub")
    if not email:
        return None
    user = db.query(User).filter(User.email == email, User.is_active == True).first()
    if user and user.person_id:
        return db.query(Person).filter(Person.id == user.person_id).first()
    return None


def require_member(member=Depends(get_current_member)):
    """Lid-endpoints die wél inloggen vereisen (bv. profiel, gezin)."""
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Niet ingelogd als lid.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return member
