from datetime import date
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.auth import get_current_admin
from app.database import get_db
from app.models.member import Member, Person, MemberPerson, Membership
from app.models.postal_codes import PostalCode
from app.models.address import Address
from app.models.contact import ContactDetail
from app.models.user import User
from app.schemas.member import (
    MemberCreate,
    MemberResponse,
    PersonCreate,
    PersonResponse,
    MembershipCreate,
    MembershipResponse,
)
from app.schemas.family import FamilyCreate

router = APIRouter(tags=["members"])


@router.get("/postal-codes")
def list_postal_codes(db: Session = Depends(get_db)):
    """Return all postal codes with their municipality names."""
    rows = db.query(PostalCode).order_by(PostalCode.postal_code).all()
    return [{"postal_code": r.postal_code, "municipality": r.municipality} for r in rows]


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


@router.post("/families", status_code=201)
def register_family(data: FamilyCreate, db: Session = Depends(get_db)):
    """Public endpoint: register a new family (member household)."""
    pc = db.query(PostalCode).filter(PostalCode.postal_code == data.postal_code).first()
    if not pc:
        raise HTTPException(status_code=422, detail=f"Onbekende postcode: {data.postal_code}")

    member = Member()
    db.add(member)
    db.flush()

    for person_data in data.members:
        person = Person(
            last_name=person_data.last_name,
            first_name=person_data.first_name,
            date_of_birth=person_data.date_of_birth,
            gender_code=person_data.gender or None,
            mobile=person_data.mobile or None,
        )
        db.add(person)
        db.flush()

        mp = MemberPerson(
            member_id=member.id,
            person_id=person.id,
            is_primary=person_data.is_primary,
        )
        db.add(mp)

        address = Address(
            person_id=person.id,
            street=data.street,
            house_number=data.house_number,
            bus_number=data.bus_number or None,
            postal_code_id=pc.id,
        )
        db.add(address)

        if person_data.phone:
            db.add(ContactDetail(person_id=person.id, contact_type_code="PHONE", value=person_data.phone, is_primary=True))
        if person_data.mobile:
            db.add(ContactDetail(person_id=person.id, contact_type_code="MOBILE", value=person_data.mobile, is_primary=not person_data.phone))
        if person_data.email:
            db.add(ContactDetail(person_id=person.id, contact_type_code="EMAIL", value=person_data.email, is_primary=True))

    db.commit()
    return {"id": member.id, "status": "registered"}
