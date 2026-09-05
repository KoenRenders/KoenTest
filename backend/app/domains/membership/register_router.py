"""Gezinnen, personen en lidmaatschappen: publieke gezinsregistratie +
admin-CRUD (verhuisd uit app/routers/members.py, #444).
"""
import logging
import time
from datetime import date
from typing import List, Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session, joinedload, selectinload

from app.domains.auth.api import get_current_admin
from app.database import get_db
from app.domains.membership.models import Membership
from app.domains.mdm.api import Member, Person, MemberPerson
from app.domains.mdm.api import PostalCode
from app.domains.mdm.api import Address
from app.domains.mdm.api import ContactDetail
from app.domains.auth.api import User
from app.domains.membership.schemas_member import (
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
from app.domains.membership import household_service as _service
from app.domains.membership.schemas_family import FamilyCreate
from app.domains.payment.api import create_payment_record, membership_price_for_date, membership_valid_period
from app.domains.audit.api import (
    snapshot_person,
    snapshot_member,
    snapshot_member_person,
    snapshot_membership,
    snapshot_address,
    snapshot_contact_detail,
)
from app.soft_delete import soft_delete
from app.domains.mail.api import send_registration_confirmation
from app.config import settings
from app.limiter import registration_limiter
from app.i18n import _


router = APIRouter(tags=["members"])


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
def create_member(
    data: MemberCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    return _service.create_member(db, data=data, _admin=_admin)


@router.get("/members/{member_id}", response_model=MemberResponse)
def get_member(
    member_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    member = db.query(Member).filter(Member.id == member_id).first()
    if not member:
        raise HTTPException(status_code=404, detail=_("Member not found"))
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
        raise HTTPException(status_code=404, detail=_("Member not found"))

    existing = (
        db.query(Membership)
        .filter(Membership.member_id == member_id, Membership.year == data.year)
        .first()
    )
    if existing:
        existing.is_active = data.is_active
        # Vul een ontbrekende geldigheidsperiode aan, anders telt het lidmaatschap
        # nooit als 'geldig' (valid_membership_until vereist valid_from/valid_to). #143
        existing.valid_from = existing.valid_from or date(data.year, 1, 1)
        existing.valid_to = existing.valid_to or date(data.year, 12, 31)
        snapshot_membership(db, existing, operation="update", action="membership_updated", source="admin_update", actor=admin.email)
        db.commit()
        db.refresh(existing)
        return existing

    membership = Membership(
        member_id=member_id,
        year=data.year,
        is_active=data.is_active,
        valid_from=date(data.year, 1, 1),
        valid_to=date(data.year, 12, 31),
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
    q: Optional[str] = Query(None, description="Zoek op naam of e-mail van een gezinslid"),
    status: Optional[str] = Query(None, description="actief | opgezegd (lidmaatschap vandaag)"),
    membership_year: Optional[int] = Query(None, description="Enkel gezinnen met een lidmaatschap dat dit jaar dekt"),
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    return _service.list_families(
        db,
        page=page,
        page_size=page_size,
        q=q,
        status=status,
        membership_year=membership_year,
        _admin=_admin,
    )


@router.get("/families/{family_id}", response_model=FamilyResponse)
def get_family(
    family_id: int,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    return _service.get_family(db, family_id=family_id, _admin=_admin)






@router.post("/families/{family_id}/memberships", status_code=201, response_model=MembershipResponse)
def create_membership_for_family(
    family_id: int,
    data: MembershipCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    return _service.create_membership_for_family(
        db,
        family_id=family_id,
        data=data,
        admin=admin,
    )


@router.delete("/families/{family_id}", status_code=204)
def delete_family(
    family_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    return _service.delete_family(db, family_id=family_id, admin=admin)


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
    return _service.update_person(db, person_id=person_id, data=data, admin=admin)


@router.put("/persons/{person_id}/address", response_model=FamilyMemberResponse)
def update_person_address(
    person_id: int,
    data: AddressUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    return _service.update_person_address(
        db,
        person_id=person_id,
        data=data,
        admin=admin,
    )


@router.put("/persons/{person_id}/contacts", response_model=FamilyMemberResponse)
def update_person_contacts(
    person_id: int,
    data: ContactsUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    return _service.update_person_contacts(
        db,
        person_id=person_id,
        data=data,
        admin=admin,
    )


@router.delete("/persons/{person_id}", status_code=204)
def delete_person(
    person_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    return _service.delete_person(db, person_id=person_id, admin=admin)


@router.post("/families/{family_id}/persons", response_model=FamilyResponse)
def add_person_to_family(
    family_id: int,
    data: PersonAddToFamily,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    return _service.add_person_to_family(
        db,
        family_id=family_id,
        data=data,
        admin=admin,
    )




@router.delete("/memberships/{membership_id}", status_code=204)
def delete_membership(
    membership_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    return _service.delete_membership(db, membership_id=membership_id, admin=admin)


@router.put("/families/{family_id}/board-member", response_model=FamilyResponse)
def assign_board_member(
    family_id: int,
    data: BoardMemberAssign,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin),
):
    return _service.assign_board_member(
        db,
        family_id=family_id,
        data=data,
        admin=admin,
    )


@router.post("/families", status_code=201, response_model=FamilyRegisteredResponse, dependencies=[Depends(registration_limiter)])
def register_family(data: FamilyCreate, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """Public endpoint: register a new family (member household)."""
    pc = db.query(PostalCode).filter(PostalCode.postal_code == data.postal_code).first()
    if not pc:
        raise HTTPException(status_code=422, detail=_("Onbekende postcode: %(postal_code)s") % {"postal_code": data.postal_code})

    # Betekenis-regel (#551): voor de bijkomende gezinsleden (naast het hoofdlid)
    # zijn geboortedatum én geslacht verplicht. Server-side afgedwongen zodat de
    # regel geldt ongeacht de caller; de client-`required` is enkel UX.
    for m in data.members:
        if (m.relation_type or "").upper() != "HOOFDLID" and (
                not m.date_of_birth or not m.resolved_gender_code):
            raise HTTPException(
                status_code=422,
                detail=_("Geboortedatum en geslacht zijn verplicht voor bijkomende gezinsleden."))

    today = date.today()

    # Dedup: voorkom een dubbel lidmaatschap (en dus dubbele betaling) voor
    # hetzelfde hoofdlid-e-mailadres in hetzelfde jaar. We blokkeren zodra er al
    # een lidmaatschap bestaat dat nog "leeft": betaald, in afwachting, of zonder
    # betaalrecord (bv. door een beheerder aangemaakt). Een eerdere inschrijving
    # waarvan de betaling mislukte/geannuleerd werd, blokkeert niet.
    hoofdlid_email = data.members[0].email
    # Zonder hoofdlid-e-mail valt er niet op e-mail te dedupliceren; sla de check over.
    if hoofdlid_email:
        existing_memberships = (
            db.query(Membership)
            .join(MemberPerson, and_(
                MemberPerson.member_id == Membership.member_id,
                MemberPerson.relation_type == "HOOFDLID",
            ))
            .join(ContactDetail, and_(
                ContactDetail.person_id == MemberPerson.person_id,
                ContactDetail.contact_type_code == "EMAIL",
                func.lower(ContactDetail.value) == hoofdlid_email.lower(),
            ))
            .filter(Membership.year == today.year)
            .all()
        )
        if existing_memberships:
            from app.domains.payment.api import PaymentRecord
            for ms in existing_memberships:
                recs = db.query(PaymentRecord).filter(
                    PaymentRecord.payable_type == "membership",
                    PaymentRecord.payable_id == ms.id,
                ).all()
                if not recs or any(r.status in ("paid", "pending") for r in recs):
                    raise HTTPException(
                        status_code=409,
                        detail=_("Er bestaat al een inschrijving voor %(year)s met dit e-mailadres. "
                                 "Neem contact op met het bestuur als dit niet klopt.") % {"year": today.year},
                    )

    member = Member()
    db.add(member)
    db.flush()
    snapshot_member(db, member, operation="insert", action="family_registered", source="registration")

    for person_data in data.members:
        person = Person(
            last_name=person_data.last_name,
            first_name=person_data.first_name,
            date_of_birth=person_data.date_of_birth,
            gender_code=person_data.resolved_gender_code,
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

        # Adres hoort enkel bij het hoofdlid (= gezinsadres). #125
        if person_data.relation_type == "HOOFDLID":
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
    description = f"Raak Millegem lidmaatschap {today.year} – {hoofdlid.last_name} {hoofdlid.first_name}"
    from app.kernel.tenant_config import tenant_base_url

    redirect_url = f"{tenant_base_url(db)}/betaling/succes?member={member.id}"

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

    # Business-event (#152): nieuw gezin/lidmaatschap aangevraagd. Geen PII.

    db.commit()

    checkout_url = None
    if data.payment_method == "online" and payment_record.gateway_payment_id:
        from app.domains.payment.api import GatewayPayment
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
                background_tasks=background_tasks,
                payment_record=payment_record,
            )
        except Exception as e:
            logger.error("Lidmaatschap bevestigingsmail mislukt naar %s: %s", hoofdlid.email, e)

    status = "pending_payment" if data.payment_method == "online" else "registered"
    return FamilyRegisteredResponse(id=member.id, status=status, checkout_url=checkout_url, amount=amount)
