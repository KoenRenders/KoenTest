import logging
import time
from datetime import date
from typing import List, Optional

logger = logging.getLogger(__name__)

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
    PersonUpdate,
    PersonAddToFamily,
    PersonListItem,
    MembershipCreate,
    MembershipResponse,
    FamilyMemberResponse,
    FamilyResponse,
    FamilyRegisteredResponse,
    PostalCodeResponse,
    PaginatedFamiliesResponse,
    PaginatedMembersResponse,
    AddressUpdate,
    ContactsUpdate,
    BoardMemberAssign,
)
from app.schemas.family import FamilyCreate
from app.domains.payment_status.service import create_payment_record, membership_price_for_date, membership_valid_period
from app.domains.audit.service import (
    snapshot_person,
    snapshot_member,
    snapshot_member_person,
    snapshot_membership,
    snapshot_address,
    snapshot_contact_detail,
)
from app.services.email import send_registration_confirmation
from app.config import settings
from app.limiter import registration_limiter

_postal_cache: Optional[list] = None
_postal_cache_ts: float = 0
POSTAL_CACHE_TTL = 3600  # 1 hour

router = APIRouter(tags=["members"])


@router.get("/postal-codes", response_model=List[PostalCodeResponse])
def list_postal_codes(db: Session = Depends(get_db)):
    """Return all postal codes with their municipality names."""
    global _postal_cache, _postal_cache_ts
    now = time.time()
    if _postal_cache is not None and (now - _postal_cache_ts) < POSTAL_CACHE_TTL:
        return _postal_cache
    rows = db.query(PostalCode).order_by(PostalCode.postal_code).all()
    _postal_cache = [PostalCodeResponse(postal_code=r.postal_code, municipality=r.municipality) for r in rows]
    _postal_cache_ts = now
    return _postal_cache


@router.get("/members", response_model=PaginatedMembersResponse)
def list_members(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    total = db.query(Member).count()
    members = db.query(Member).order_by(Member.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    return PaginatedMembersResponse(
        items=members,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.post("/members", response_model=MemberResponse)
def create_member(data: MemberCreate, db: Session = Depends(get_db)):
    member = Member()
    db.add(member)
    db.flush()
    snapshot_member(db, member, operation="insert", action="member_created", source="system")

    for person_data in data.persons:
        person = Person(
            last_name=person_data.last_name,
            first_name=person_data.first_name,
            date_of_birth=person_data.date_of_birth,
            gender_code=person_data.gender_code or person_data.gender or None,
        )
        db.add(person)
        db.flush()
        snapshot_person(db, person, operation="insert", action="person_created", source="system")

        mp = MemberPerson(
            member_id=member.id,
            person_id=person.id,
            relation_type=person_data.relation_type,
        )
        db.add(mp)
        db.flush()
        snapshot_member_person(db, mp, operation="insert", action="person_created", source="system")

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
    admin: User = Depends(get_current_admin),
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
        snapshot_membership(db, existing, operation="update", action="membership_updated", source="admin_update", actor=admin.email)
        db.commit()
        db.refresh(existing)
        return existing

    membership = Membership(
        member_id=member_id,
        year=data.year,
        is_active=data.is_active,
    )
    db.add(membership)
    db.flush()
    snapshot_membership(db, membership, operation="insert", action="membership_created", source="admin_manual", actor=admin.email)
    db.commit()
    db.refresh(membership)
    return membership


@router.get("/families", response_model=PaginatedFamiliesResponse)
def list_families(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    total = db.query(Member).count()
    families = db.query(Member).order_by(Member.created_at.desc()).offset((page - 1) * page_size).limit(page_size).all()
    result = [_build_family_response(m) for m in families]
    return PaginatedFamiliesResponse(
        items=result,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=(total + page_size - 1) // page_size,
    )


@router.get("/families/{family_id}", response_model=FamilyResponse)
def get_family(
    family_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    m = db.query(Member).filter(Member.id == family_id).first()
    if not m:
        raise HTTPException(status_code=404, detail="Family not found")
    return _build_family_response(m)


def _person_to_schema(person: Person, relation_type: str) -> FamilyMemberResponse:
    email = next((c.value for c in person.contact_details if c.contact_type_code == "EMAIL"), None)
    phone = next((c.value for c in person.contact_details if c.contact_type_code == "PHONE"), None)
    mobile = next((c.value for c in person.contact_details if c.contact_type_code == "MOBILE"), None)
    return FamilyMemberResponse(
        id=person.id,
        last_name=person.last_name,
        first_name=person.first_name,
        date_of_birth=person.date_of_birth,
        gender=person.gender_code,
        email=email,
        phone=phone,
        mobile=mobile,
        relation_type=relation_type,
    )


def _build_family_response(m: Member) -> FamilyResponse:
    primary = next((mp.person for mp in m.member_persons if mp.relation_type == "HOOFDLID"), None)
    address = primary.address if primary else None
    board_member = PersonListItem(
        id=m.board_member.id,
        last_name=m.board_member.last_name,
        first_name=m.board_member.first_name,
    ) if m.board_member else None
    return FamilyResponse(
        id=m.id,
        street=address.street if address else "",
        house_number=address.house_number if address else "",
        bus_number=address.bus_number if address else None,
        postal_code=address.postal_code.postal_code if address and address.postal_code else "",
        municipality=address.postal_code.municipality if address and address.postal_code else "",
        members=[_person_to_schema(mp.person, mp.relation_type) for mp in m.member_persons],
        memberships=[MembershipResponse.model_validate(ms) for ms in m.memberships],
        board_member=board_member,
    )


@router.post("/families/{family_id}/memberships", status_code=201, response_model=MembershipResponse)
def create_membership_for_family(
    family_id: int,
    data: MembershipCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    member = db.query(Member).filter(Member.id == family_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Family not found")
    membership = Membership(member_id=family_id, year=data.year, is_active=data.is_active)
    db.add(membership)
    db.flush()
    snapshot_membership(db, membership, operation="insert", action="membership_created", source="admin_manual", actor=admin.email)
    db.commit()
    db.refresh(membership)
    return MembershipResponse.model_validate(membership)


@router.delete("/families/{family_id}", status_code=204)
def delete_family(
    family_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    member = db.query(Member).filter(Member.id == family_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Family not found")

    # Eerst alles als delete-snapshot vastleggen, dan pas verwijderen.
    for ms in member.memberships:
        snapshot_membership(db, ms, operation="delete", action="family_deleted", source="admin_manual", actor=admin.email)
    for mp in member.member_persons:
        person = mp.person
        for contact in person.contact_details:
            snapshot_contact_detail(db, contact, operation="delete", action="family_deleted", source="admin_manual", actor=admin.email)
        if person.address:
            snapshot_address(db, person.address, operation="delete", action="family_deleted", source="admin_manual", actor=admin.email)
        snapshot_member_person(db, mp, operation="delete", action="family_deleted", source="admin_manual", actor=admin.email)
        snapshot_person(db, person, operation="delete", action="family_deleted", source="admin_manual", actor=admin.email)
    snapshot_member(db, member, operation="delete", action="family_deleted", source="admin_manual", actor=admin.email)

    for mp in member.member_persons:
        person = mp.person
        if person.address:
            db.delete(person.address)
        db.delete(person)

    db.delete(member)
    db.commit()


@router.get("/persons", response_model=List[PersonListItem])
def list_persons(
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    return db.query(Person).order_by(Person.last_name, Person.first_name).all()


@router.put("/persons/{person_id}", response_model=FamilyMemberResponse)
def update_person(
    person_id: int,
    data: PersonUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(person, field, value)
    snapshot_person(db, person, operation="update", action="person_updated", source="admin_update", actor=admin.email)
    db.commit()
    db.refresh(person)
    mp = next((mp for mp in person.member_persons), None)
    return _person_to_schema(person, mp.relation_type if mp else "HOOFDLID")


@router.put("/persons/{person_id}/address", response_model=FamilyMemberResponse)
def update_person_address(
    person_id: int,
    data: AddressUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    address = person.address
    if not address:
        raise HTTPException(status_code=404, detail="Address not found")
    if data.postal_code is not None:
        pc = db.query(PostalCode).filter(PostalCode.postal_code == data.postal_code).first()
        if not pc:
            raise HTTPException(status_code=422, detail=f"Onbekende postcode: {data.postal_code}")
        address.postal_code_id = pc.id
    for field in ("street", "house_number"):
        value = getattr(data, field)
        if value is not None:
            setattr(address, field, value)
    if data.bus_number is not None or "bus_number" in (data.model_fields_set or set()):
        address.bus_number = data.bus_number or None
    snapshot_address(db, address, operation="update", action="address_updated", source="admin_update", actor=admin.email)
    db.commit()
    db.refresh(person)
    mp = next((mp for mp in person.member_persons), None)
    return _person_to_schema(person, mp.relation_type if mp else "HOOFDLID")


@router.put("/persons/{person_id}/contacts", response_model=FamilyMemberResponse)
def update_person_contacts(
    person_id: int,
    data: ContactsUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")

    def _upsert_contact(type_code: str, value: Optional[str]):
        existing = next((c for c in person.contact_details if c.contact_type_code == type_code), None)
        if value:
            if existing:
                existing.value = value
                db.flush()
                snapshot_contact_detail(db, existing, operation="update", action="contacts_updated", source="admin_update", actor=admin.email)
            else:
                contact = ContactDetail(person_id=person_id, contact_type_code=type_code, value=value, is_primary=True)
                person.contact_details.append(contact)
                db.flush()
                snapshot_contact_detail(db, contact, operation="insert", action="contacts_updated", source="admin_update", actor=admin.email)
        elif existing:
            snapshot_contact_detail(db, existing, operation="delete", action="contacts_updated", source="admin_update", actor=admin.email)
            person.contact_details.remove(existing)

    _upsert_contact("EMAIL", data.email)
    _upsert_contact("PHONE", data.phone)
    _upsert_contact("MOBILE", data.mobile)
    db.commit()
    db.refresh(person)
    mp = next((mp for mp in person.member_persons), None)
    return _person_to_schema(person, mp.relation_type if mp else "HOOFDLID")


@router.delete("/persons/{person_id}", status_code=204)
def delete_person(
    person_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    person = db.query(Person).filter(Person.id == person_id).first()
    if not person:
        raise HTTPException(status_code=404, detail="Person not found")
    for contact in person.contact_details:
        snapshot_contact_detail(db, contact, operation="delete", action="person_deleted", source="admin_manual", actor=admin.email)
    for mp in person.member_persons:
        snapshot_member_person(db, mp, operation="delete", action="person_deleted", source="admin_manual", actor=admin.email)
        db.delete(mp)
    if person.address:
        snapshot_address(db, person.address, operation="delete", action="person_deleted", source="admin_manual", actor=admin.email)
        db.delete(person.address)
    snapshot_person(db, person, operation="delete", action="person_deleted", source="admin_manual", actor=admin.email)
    db.delete(person)
    db.commit()


@router.post("/families/{family_id}/persons", response_model=FamilyResponse)
def add_person_to_family(
    family_id: int,
    data: PersonAddToFamily,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    member = db.query(Member).filter(Member.id == family_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Family not found")
    primary = next((mp.person for mp in member.member_persons if mp.is_primary), None)
    primary_address = primary.address if primary else None

    person = Person(
        last_name=data.last_name,
        first_name=data.first_name,
        date_of_birth=data.date_of_birth,
        gender_code=data.gender_code,
    )
    db.add(person)
    db.flush()
    snapshot_person(db, person, operation="insert", action="person_added_to_family", source="admin_manual", actor=admin.email)

    mp = MemberPerson(member_id=family_id, person_id=person.id, relation_type=data.relation_type)
    db.add(mp)
    db.flush()
    snapshot_member_person(db, mp, operation="insert", action="person_added_to_family", source="admin_manual", actor=admin.email)

    if primary_address:
        address = Address(
            person_id=person.id,
            street=primary_address.street,
            house_number=primary_address.house_number,
            bus_number=primary_address.bus_number,
            postal_code_id=primary_address.postal_code_id,
        )
        db.add(address)
        db.flush()
        snapshot_address(db, address, operation="insert", action="person_added_to_family", source="admin_manual", actor=admin.email)

    for type_code, value in (("EMAIL", data.email), ("PHONE", data.phone), ("MOBILE", data.mobile)):
        if value:
            contact = ContactDetail(person_id=person.id, contact_type_code=type_code, value=value, is_primary=True)
            db.add(contact)
            db.flush()
            snapshot_contact_detail(db, contact, operation="insert", action="person_added_to_family", source="admin_manual", actor=admin.email)

    db.commit()
    db.refresh(member)
    return _build_family_response(member)


@router.delete("/memberships/{membership_id}", status_code=204)
def delete_membership(
    membership_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    membership = db.query(Membership).filter(Membership.id == membership_id).first()
    if not membership:
        raise HTTPException(status_code=404, detail="Membership not found")
    snapshot_membership(db, membership, operation="delete", action="membership_deleted", source="admin_manual", actor=admin.email)
    db.delete(membership)
    db.commit()


@router.put("/families/{family_id}/board-member", response_model=FamilyResponse)
def assign_board_member(
    family_id: int,
    data: BoardMemberAssign,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    member = db.query(Member).filter(Member.id == family_id).first()
    if not member:
        raise HTTPException(status_code=404, detail="Family not found")
    if data.person_id is not None:
        person = db.query(Person).filter(Person.id == data.person_id).first()
        if not person:
            raise HTTPException(status_code=404, detail="Person not found")
    member.board_member_id = data.person_id
    snapshot_member(db, member, operation="update", action="board_member_assigned", source="admin_update", actor=admin.email)
    db.commit()
    db.refresh(member)
    return _build_family_response(member)


@router.post("/families", status_code=201, response_model=FamilyRegisteredResponse, dependencies=[Depends(registration_limiter)])
def register_family(data: FamilyCreate, db: Session = Depends(get_db)):
    """Public endpoint: register a new family (member household)."""
    pc = db.query(PostalCode).filter(PostalCode.postal_code == data.postal_code).first()
    if not pc:
        raise HTTPException(status_code=422, detail=f"Onbekende postcode: {data.postal_code}")

    member = Member()
    db.add(member)
    db.flush()
    snapshot_member(db, member, operation="insert", action="family_registered", source="registration")

    for person_data in data.members:
        person = Person(
            last_name=person_data.last_name,
            first_name=person_data.first_name,
            date_of_birth=person_data.date_of_birth,
            gender_code=person_data.gender or None,
        )
        db.add(person)
        db.flush()
        snapshot_person(db, person, operation="insert", action="family_registered", source="registration")

        mp = MemberPerson(
            member_id=member.id,
            person_id=person.id,
            relation_type=person_data.relation_type,
        )
        db.add(mp)
        db.flush()
        snapshot_member_person(db, mp, operation="insert", action="family_registered", source="registration")

        address = Address(
            person_id=person.id,
            street=data.street,
            house_number=data.house_number,
            bus_number=data.bus_number or None,
            postal_code_id=pc.id,
        )
        db.add(address)
        db.flush()
        snapshot_address(db, address, operation="insert", action="family_registered", source="registration")

        contacts = []
        if person_data.phone:
            contacts.append(ContactDetail(person_id=person.id, contact_type_code="PHONE", value=person_data.phone, is_primary=True))
        if person_data.mobile:
            contacts.append(ContactDetail(person_id=person.id, contact_type_code="MOBILE", value=person_data.mobile, is_primary=not person_data.phone))
        if person_data.email:
            contacts.append(ContactDetail(person_id=person.id, contact_type_code="EMAIL", value=person_data.email, is_primary=True))
        for contact in contacts:
            db.add(contact)
        if contacts:
            db.flush()
            for contact in contacts:
                snapshot_contact_detail(db, contact, operation="insert", action="family_registered", source="registration")

    # Annual membership record
    today = date.today()
    valid_from, valid_to = membership_valid_period(today)
    membership = Membership(
        member_id=member.id,
        year=today.year,
        is_active=False,
        valid_from=valid_from,
        valid_to=valid_to,
    )
    db.add(membership)
    db.flush()
    snapshot_membership(db, membership, operation="insert", action="family_registered", source="registration")

    # Payment
    amount = membership_price_for_date(today)
    hoofdlid = data.members[0]
    description = f"KWB Millegem lidmaatschap {today.year} – {hoofdlid.last_name} {hoofdlid.first_name}"
    redirect_url = f"{settings.frontend_url}/betaling/succes?member={member.id}"

    try:
        payment_record = create_payment_record(
            db=db,
            payable_type="membership",
            payable_id=membership.id,
            amount=amount,
            method=data.payment_method,
            redirect_url=redirect_url,
            description=description,
            audit_source="registration",
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))

    db.commit()

    checkout_url = None
    if data.payment_method == "online" and payment_record.gateway_payment_id:
        from app.domains.payment_gateway.models import GatewayPayment
        gp = db.query(GatewayPayment).filter(GatewayPayment.id == payment_record.gateway_payment_id).first()
        if gp:
            checkout_url = gp.checkout_url

    if hoofdlid.email:
        try:
            send_registration_confirmation(
                to_email=hoofdlid.email,
                name=f"{hoofdlid.first_name} {hoofdlid.last_name}",
                family=member,
                data=data,
                pc_municipality=pc.municipality if pc else "",
            )
        except Exception as e:
            logger.error("Lidmaatschap bevestigingsmail mislukt naar %s: %s", hoofdlid.email, e)

    status = "pending_payment" if data.payment_method == "online" else "registered"
    return FamilyRegisteredResponse(id=member.id, status=status, checkout_url=checkout_url, amount=amount)
