from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel

from app.auth import get_current_admin
from app.database import get_db
from app.models.user import User, UserRole
from app.models.member import Person

router = APIRouter(prefix="/users", tags=["admin-users"])


# ── Schemas ───────────────────────────────────────────────────────────────────

class UserRoleOut(BaseModel):
    role_code: str
    model_config = {"from_attributes": True}


class PersonRef(BaseModel):
    id: int
    first_name: str
    last_name: str
    model_config = {"from_attributes": True}


class UserOut(BaseModel):
    id: int
    email: str
    is_active: bool
    person_id: Optional[int] = None
    person: Optional[PersonRef] = None
    roles: List[UserRoleOut] = []
    model_config = {"from_attributes": True}


class UserCreate(BaseModel):
    email: str
    is_active: bool = True
    person_id: Optional[int] = None
    role_codes: List[str] = []


class UserUpdate(BaseModel):
    email: Optional[str] = None
    is_active: Optional[bool] = None
    person_id: Optional[int] = None
    role_codes: Optional[List[str]] = None


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.get("", response_model=List[UserOut])
def list_users(db: Session = Depends(get_db), _=Depends(get_current_admin)):
    return db.query(User).order_by(User.email).all()


@router.post("", response_model=UserOut, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db), _=Depends(get_current_admin)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=400, detail="E-mailadres is al in gebruik.")
    if body.person_id:
        if not db.query(Person).filter(Person.id == body.person_id).first():
            raise HTTPException(status_code=404, detail="Persoon niet gevonden.")
    user = User(email=body.email, is_active=body.is_active, person_id=body.person_id)
    db.add(user)
    db.flush()
    for code in body.role_codes:
        db.add(UserRole(user_id=user.id, role_code=code))
    db.commit()
    db.refresh(user)
    return user


@router.put("/{user_id}", response_model=UserOut)
def update_user(user_id: int, body: UserUpdate, db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin)):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Gebruiker niet gevonden.")
    if body.email is not None:
        existing = db.query(User).filter(User.email == body.email, User.id != user_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="E-mailadres is al in gebruik.")
        user.email = body.email
    if body.is_active is not None:
        user.is_active = body.is_active
    if body.person_id is not None:
        if not db.query(Person).filter(Person.id == body.person_id).first():
            raise HTTPException(status_code=404, detail="Persoon niet gevonden.")
        user.person_id = body.person_id
    elif "person_id" in body.model_fields_set and body.person_id is None:
        user.person_id = None
    if body.role_codes is not None:
        db.query(UserRole).filter(UserRole.user_id == user_id).delete()
        for code in body.role_codes:
            db.add(UserRole(user_id=user_id, role_code=code))
    db.commit()
    db.refresh(user)
    return user


@router.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, db: Session = Depends(get_db), current_admin: User = Depends(get_current_admin)):
    if current_admin.id == user_id:
        raise HTTPException(status_code=400, detail="Je kan jezelf niet verwijderen.")
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Gebruiker niet gevonden.")
    db.delete(user)
    db.commit()
