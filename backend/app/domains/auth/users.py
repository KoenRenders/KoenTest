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


def is_platform_workspace(db: Session) -> bool:
    """Is de actieve werkruimte het platform? (Koens aanscherping van 16 sep:
    OPERATOR wordt alléén daar toegekend, en alleen daar beheert een scherm
    meerdere werkruimtes tegelijk.)"""
    from app.domains.mdm.api import platform_tenant_id

    platform = platform_tenant_id(db)
    return platform is not None and _actieve_werkruimte() == platform


def _ken_rollen_toe(db: Session, user_id: int, codes: List[str],
                    actor_roles: set | None) -> None:
    """Vervang de rollen van een gebruiker BINNEN de actieve werkruimte (#963).

    Rijen van andere werkruimtes blijven onaangeroerd — ADMIN van werkruimte A
    beheert werkruimte B niet (Koens besluit 3). OPERATOR is de platformbrede
    rij (tenant_id NULL, besluit 1) en wordt ALLEEN binnen het platform
    toegekend (aanscherping 16 sep) — dit is de werkruimte-variant, dus een
    OPERATOR-code hier is altijd een 403, nooit een stille escalatie."""
    from app.domains.auth.models import UserRole

    actief = _actieve_werkruimte()
    nieuwe = set(codes)
    if "OPERATOR" in nieuwe:
        raise HTTPException(
            status_code=403,
            detail=_("OPERATOR wordt alleen binnen het platform toegekend."))
    db.query(UserRole).filter(UserRole.user_id == user_id,
                              UserRole.tenant_id == actief).delete()
    for code in nieuwe:
        db.add(UserRole(user_id=user_id, role_code=code, tenant_id=actief))


def set_roles_for_workspaces(db: Session, user_id: int,
                             per_werkruimte: dict, operator: bool,
                             actor_roles: set | None) -> None:
    """Het platform-gebruikersbeheer (Koen, 16 sep): rollen voor MEERDERE
    werkruimtes in één beweging — zo maakt een OPERATOR de eerste gebruikers
    van een nieuwe tenant aan en beheert hij ze namens de afdelingen.

    ``per_werkruimte`` is {tenant_id: [codes]} voor élke getoonde werkruimte
    (het formulier toont ze allemaal, dus vervangen per werkruimte is juist).
    ``operator`` stuurt de platformbrede rij; die wijzigen mag alleen een
    OPERATOR — het vinkje is voor anderen verborgen en een omzeild formulier
    krijgt hier de 403."""
    from app.domains.auth.models import UserRole

    for codes in per_werkruimte.values():
        _validate_role_codes(db, [c for c in codes if c != "OPERATOR"])
        if "OPERATOR" in codes:
            raise HTTPException(
                status_code=403,
                detail=_("OPERATOR is platformbreed en hoort niet bij één "
                         "werkruimte."))
    mag_operator = bool(actor_roles and "OPERATOR" in actor_roles)
    platform_rij = (db.query(UserRole)
                    .filter(UserRole.user_id == user_id,
                            UserRole.role_code == "OPERATOR",
                            UserRole.tenant_id.is_(None)).first())
    if operator != (platform_rij is not None) and not mag_operator:
        raise HTTPException(
            status_code=403,
            detail=_("Alleen een OPERATOR kan de OPERATOR-rol toekennen."))
    for tenant_id, codes in per_werkruimte.items():
        db.query(UserRole).filter(UserRole.user_id == user_id,
                                  UserRole.tenant_id == tenant_id).delete()
        for code in set(codes):
            db.add(UserRole(user_id=user_id, role_code=code,
                            tenant_id=tenant_id))
    if mag_operator:
        if operator and platform_rij is None:
            db.add(UserRole(user_id=user_id, role_code="OPERATOR",
                            tenant_id=None))
        elif not operator and platform_rij is not None:
            db.delete(platform_rij)
    # Zelf committen, zoals create_user/update_user: de UI-laag mag geen
    # sessiebeheer doen (laaggrens, #635 regel 2).
    db.commit()


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
    # CR-12 phase 2: this used to say `notin_(["USER", "MEMBER"])`. Those two
    # are now retired codes (`is_active = false`), and `code_labels()` by
    # definition returns only the active ones — so the exception has gone
    # because the list itself carries it, instead of every screen having to
    # remember it again. The order comes from `sort_order`.
    from app.domains.auth.models import RoleCode
    from app.kernel.codes import code_labels

    active_codes = [code for code, _label in code_labels("role")]
    return (db.query(RoleCode).filter(RoleCode.code.in_(active_codes))
            .order_by(RoleCode.sort_order).all())


def role_options(rollen, taal: str = "nl") -> list[tuple[str, str]]:
    """De toekenbare rollen als (code, leesbaar label) — voor een keuzelijst.

    Het label is `value` uit de codetabel ("Beheerder", "Penningmeester") en niet
    de code. Tussen knoppen viel een ruwe `FINANCE` weg te kijken; in een
    keuzelijst leest ze als een bug (#1079).

    Neemt de rijen die de aanroeper al heeft i.p.v. zelf te queryen: het scherm
    toont dezelfde rollen als vinkjes, en twee queries op één codetabel zijn twee
    plekken die kunnen uiteenlopen.

    CR-12 phase 2: this used to do the same manual per-language collapsing as
    `legal_form_options`, because the code table had one row per
    (code, language). With the split shape there is one row per code and
    `code_label()` does the fallback — language, then `nl`, then the code
    itself.
    """
    from app.kernel.codes import code_label

    return [(rij.code, code_label("role", rij.code, language=taal))
            for rij in sorted(rollen, key=lambda r: r.sort_order)]
