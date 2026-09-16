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

def _actieve_werkruimte() -> int:
    from app.kernel.tenancy import DEFAULT_TENANT_ID, current_tenant_id

    return current_tenant_id.get() or DEFAULT_TENANT_ID


def _ken_rollen_toe(db: Session, user_id: int, codes: List[str],
                    actor_roles: set | None) -> None:
    """Vervang de rollen van een gebruiker BINNEN de actieve werkruimte (#963).

    Rijen van andere werkruimtes blijven onaangeroerd — ADMIN van werkruimte A
    beheert werkruimte B niet (Koens besluit 3). OPERATOR is de platformbrede
    rij (tenant_id NULL, besluit 1) en mag alleen door een OPERATOR gezet of
    weggenomen worden; een ADMIN die hem probeert toe te kennen krijgt een
    403 in plaats van een stille escalatie."""
    from app.domains.auth.models import UserRole

    actief = _actieve_werkruimte()
    nieuwe = set(codes)
    mag_operator = bool(actor_roles and "OPERATOR" in actor_roles)
    platform_rij = (db.query(UserRole)
                    .filter(UserRole.user_id == user_id,
                            UserRole.role_code == "OPERATOR",
                            UserRole.tenant_id.is_(None)).first())
    if "OPERATOR" in nieuwe and platform_rij is None and not mag_operator:
        raise HTTPException(
            status_code=403,
            detail=_("Alleen een OPERATOR kan de OPERATOR-rol toekennen."))
    db.query(UserRole).filter(UserRole.user_id == user_id,
                              UserRole.tenant_id == actief).delete()
    for code in nieuwe - {"OPERATOR"}:
        db.add(UserRole(user_id=user_id, role_code=code, tenant_id=actief))
    if mag_operator:
        if "OPERATOR" in nieuwe and platform_rij is None:
            db.add(UserRole(user_id=user_id, role_code="OPERATOR",
                            tenant_id=None))
        elif "OPERATOR" not in nieuwe and platform_rij is not None:
            db.delete(platform_rij)


def _actor_roles(db: Session, admin) -> set | None:
    """Rollen van de handelende beheerder, of None wanneer die onbekend is
    (dan geldt de strengste lezing: geen OPERATOR-bevoegdheid)."""
    from app.domains.auth.service import get_user_roles

    return get_user_roles(db, admin.email) if admin is not None else None


def _validate_role_codes(db: Session, codes: List[str]) -> None:
    """Rolcodes valideren tegen de codetabel. Sinds migratie 076 is er bewust
    geen FK meer naar public.role_codes (§8: geen cross-schema FK's) — deze
    check is de servicelaag-vervanger."""
    if not codes:
        return
    from app.domains.auth.models import RoleCode

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
    _ken_rollen_toe(db, user.id, body.role_codes, _actor_roles(db, _admin))
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
        _ken_rollen_toe(db, user_id, body.role_codes, _actor_roles(db, _admin))
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


def list_assignable_roles(db):
    """De rollen die je in gebruikersbeheer kan toekennen (#458/#521).

    USER en MEMBER zijn dode rollen: geen enkele autorisatie hangt eraan — de
    backoffice draait op ADMIN/FINANCE/OPERATOR en lidmaatschap is data-gedreven
    via Membership. Ze uit de keuzelijst filteren voorkomt zinloze, verwarrende
    vinkjes, en dus ook zinloze filterchips.
    """
    from app.domains.auth.models import RoleCode

    return (db.query(RoleCode).filter(RoleCode.code.notin_(["USER", "MEMBER"]))
            .order_by(RoleCode.code).all())
