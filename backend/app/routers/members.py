from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models.member import Member, Person, MemberPerson, Membership
from app.models.user import User
from app.schemas.member import (
    MemberCreate,
    MemberResponse,
    PersonCreate,
    PersonResponse,
    MembershipCreate,
    MembershipResponse,
)

router = APIRouter(tags=["members"])


@router.get("/members", response_model=List[MemberResponse])
def list_members(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    return db.query(Member).order_by(Member.created_at.desc()).all()


@router.post("/members", response_model=MemberResponse)
def create_member(data: MemberCreate, db: Session = Depends(get_db)):
    member = Member()
    db.add(member)
    db.flush()

    for person_data in data.persons:
        person = Person(
            last_name=person_data.last_name,
            first_name=person_data.first_name,
            date_of_birth=person_data.date_of_birth,
            gender_code=person_data.gender_code,
        )
        db.add(person)
        db.flush()

        mp = MemberPerson(
            member_id=member.id,
            person_id=person.id,
            is_primary=person_data.is_primary,
        )
        db.add(mp)

    db.commit()
    db.refresh(member)
    return member


@router.get("/members/{member_id}", response_model=MemberResponse)
def get_member(
    member_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    return member


@router.get("/memberships", response_model=List[MembershipResponse])
def list_memberships(
    year: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    query = db.query(Membership)
    if year is not None:
        query = query.filter(Membership.year == year)
    return query.order_by(Membership.created_at.desc()).all()


@router.post("/members/{member_id}/memberships", response_model=MembershipResponse)
def create_membership(
    member_id: int,
    data: MembershipCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")

    existing = (
        db.query(Membership)
        .filter(Membership.member_id == member_id, Membership.year == data.year)
        .first()
    )
    if existing:
        existing.is_active = data.is_active
        db.commit()
        db.refresh(existing)
        return existing

    membership = Membership(
        member_id=member_id,
        year=data.year,
        is_active=data.is_active,
    )
    db.add(membership)
    db.commit()
    db.refresh(membership)
    return membership
