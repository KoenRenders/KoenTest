from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models.family import Family, FamilyMember, Membership
from app.models.user import AdminUser
from app.schemas.family import (
    FamilyCreate,
    FamilyUpdate,
    FamilyResponse,
    FamilyMemberCreate,
    FamilyMemberResponse,
    MembershipCreate,
    MembershipResponse,
)
from app.services.email import send_registration_confirmation

router = APIRouter(tags=["families"])


@router.get("/families", response_model=List[FamilyResponse])
def list_families(
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    return db.query(Family).order_by(Family.created_at.desc()).all()


@router.post("/families", response_model=FamilyResponse)
def create_family(data: FamilyCreate, db: Session = Depends(get_db)):
    family = Family(
        street=data.street,
        house_number=data.house_number,
        bus_number=data.bus_number,
        postal_code=data.postal_code,
        municipality=data.municipality,
    )
    db.add(family)
    db.flush()

    for member_data in data.members:
        member = FamilyMember(
            family_id=family.id,
            last_name=member_data.last_name,
            first_name=member_data.first_name,
            date_of_birth=member_data.date_of_birth,
            gender=member_data.gender,
            email=member_data.email,
            phone=member_data.phone,
            is_primary=member_data.is_primary,
        )
        db.add(member)

    db.commit()
    db.refresh(family)

    # Try to send confirmation email to primary member
    primary = next((m for m in family.members if m.is_primary), None)
    if primary and primary.email:
        try:
            send_registration_confirmation(
                to_email=primary.email,
                name=f"{primary.first_name} {primary.last_name}",
                family=family,
            )
        except Exception:
            pass  # Email failure should not block registration

    return family


@router.get("/families/{family_id}", response_model=FamilyResponse)
def get_family(
    family_id: int,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    family = db.query(Family).filter(Family.id == family_id).first()
    if not family:
        raise HTTPException(status_code=404, detail="Family not found")
    return family


@router.put("/families/{family_id}", response_model=FamilyResponse)
def update_family(
    family_id: int,
    data: FamilyUpdate,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    family = db.query(Family).filter(Family.id == family_id).first()
    if not family:
        raise HTTPException(status_code=404, detail="Family not found")

    for field, value in data.model_dump(exclude_none=True).items():
        setattr(family, field, value)

    db.commit()
    db.refresh(family)
    return family


@router.post("/families/{family_id}/members", response_model=FamilyMemberResponse)
def add_family_member(
    family_id: int,
    data: FamilyMemberCreate,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    family = db.query(Family).filter(Family.id == family_id).first()
    if not family:
        raise HTTPException(status_code=404, detail="Family not found")

    member = FamilyMember(
        family_id=family_id,
        last_name=data.last_name,
        first_name=data.first_name,
        date_of_birth=data.date_of_birth,
        gender=data.gender,
        email=data.email,
        phone=data.phone,
        is_primary=data.is_primary,
    )
    db.add(member)
    db.commit()
    db.refresh(member)
    return member


@router.get("/memberships", response_model=List[MembershipResponse])
def list_memberships(
    year: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    query = db.query(Membership)
    if year is not None:
        query = query.filter(Membership.year == year)
    return query.order_by(Membership.created_at.desc()).all()


@router.post("/families/{family_id}/memberships", response_model=MembershipResponse)
def create_membership(
    family_id: int,
    data: MembershipCreate,
    db: Session = Depends(get_db),
    _admin: AdminUser = Depends(get_current_admin),
):
    family = db.query(Family).filter(Family.id == family_id).first()
    if not family:
        raise HTTPException(status_code=404, detail="Family not found")

    existing = (
        db.query(Membership)
        .filter(Membership.family_id == family_id, Membership.year == data.year)
        .first()
    )
    if existing:
        existing.is_active = data.is_active
        db.commit()
        db.refresh(existing)
        return existing

    membership = Membership(
        family_id=family_id,
        year=data.year,
        is_active=data.is_active,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership
