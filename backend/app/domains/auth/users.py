from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.domains.auth.service import get_current_admin
from app.database import get_db
from app.domains.auth.models import User, UserRole
from app.i18n import _

router = APIRouter(prefix="/users", tags=["users"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class UserRoleOut(BaseModel):
    role_code: str
    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: int
    email: str
    is_active: bool
    roles: List[UserRoleOut] = []
    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: str
    is_active: bool = True
    role_codes: List[str] = []


class UserUpdate(BaseModel):
    email: Optional[str] = None
    is_active: Optional[bool] = None
    role_codes: Optional[List[str]] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────
#
# Beheer van backoffice-accounts en hun rollen. Lid-zijn hoort hier NIET thuis:
# dat wordt afgeleid uit het leden-domein (e-mail -> Person) en heeft geen
# user-record nodig.

def _validate_role_codes(db: Session, codes: List[str]) -> None:
    """Rolcodes valideren tegen de codetabel. Sinds migratie 076 is er bewust
    geen FK meer naar public.role_codes (§8: geen cross-schema FK's) — deze
    check is de servicelaag-vervanger."""
    if not codes:
        return
    from app.models.codes import RoleCode

    known = {r.code for r in db.query(RoleCode.code).all()}
    unknown = [c for c in codes if c not in known]
    if unknown:
        raise HTTPException(status_code=400, detail=_("Onbekende rolcode(s): %(codes)s") % {"codes": ', '.join(unknown)})


@router.get("", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    return db.query(User).order_by(User.email).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail=_("E-mailadres is al in gebruik."))
    _validate_role_codes(db, body.role_codes)
    user = User(email=body.email, is_active=body.is_active)
    db.add(user)
    db.flush()
    for code in body.role_codes:
        db.add(UserRole(user_id=user.id, role_code=code))
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db), _admin=Depends(get_current_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=_("Gebruiker niet gevonden."))
    if body.email is not None:
        existing = db.query(User).filter(User.email == body.email, User.id != user_id).first()
        if existing:
            raise HTTPException(status_code=400, detail=_("E-mailadres is al in gebruik."))
        user.email = body.email
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.role_codes is not None:
        _validate_role_codes(db, body.role_codes)
        db.query(UserRole).filter(UserRole.user_id == user_id).delete()
        for code in body.role_codes:
            db.add(UserRole(user_id=user_id, role_code=code))
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin)):
    if current_admin.id == user_id:
        raise HTTPException(status_code=400, detail=_("Je kan jezelf niet verwijderen."))
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail=_("Gebruiker niet gevonden."))
    from app.soft_delete import soft_delete
    soft_delete(user)
    db.commit()
