"""Gezinnen, personen en lidmaatschappen: publieke gezinsregistratie +
admin-CRUD (verhuisd uit app/routers/members.py, #444).
"""

import logging
from datetime import date

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.database import get_db

# #1110: het schrijven van een gezin staat in household_service, dus de snapshots
# daarvan ook. Wat hier rest is het lidmaatschap dat deze router zelf bijwerkt.
from app.domains.audit.api import (  # noqa: F401
    PUBLIEKE_ACTOR,
    snapshot_membership,
)
from app.domains.auth.api import User, get_current_admin
from app.domains.mdm.api import (
    CONTACT,
    ContactDetail,
    MemberPerson,
    PaymentMethod,
    Person,
    PostalCode,
    RelationType,
)
from app.domains.membership import household_service as _service
from app.domains.membership.models import KnownAddress, Membership
from app.domains.membership.schemas_family import FamilyCreate
from app.domains.membership.schemas_member import (
    FamilyRegisteredResponse,
    MemberCreate,
    MemberResponse,
)
from app.domains.payment.api import create_payment_record, membership_price_for_date
from app.i18n import _
from app.kernel.contracts.membership import FamilyRegistered
from app.kernel.events import publish

logger = logging.getLogger(__name__)

router = APIRouter(tags=["members"])


@router.post("/members", response_model=MemberResponse)
def create_member(
    data: MemberCreate,
    db: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin),
):
    # #713: de parameter heet `admin` sinds die de auditregel écht tekent.
    return _service.create_member(db, data=data, admin=_admin)


# No route of its own since CR-13 phase 4b (#1251): `POST /api/v1/families` had no
# caller. This is the function behind `membership.api.register_family`, which the
# public form calls; it stays in this file until phase 4c moves it.
def register_family(
    data: FamilyCreate,
    background_tasks: BackgroundTasks,
    *,
    db: Session,
    signed_in: Person | None,
) -> FamilyRegisteredResponse:
    """The public door: register a new family (member household).

    Het schrijven zelf — gezin, personen, adres, contactgegevens, lidmaatschap —
    staat sinds #1110 in `household_service.create_family_with_members`, want de
    beheerkant maakt hetzelfde aan en deed dat met een eigen, kortere versie. Wat
    hier blijft is wat álléén voor de publieke ingang geldt: de dedup op het
    hoofdlid-e-mailadres, de betaling en de bevestigingsmail. De postcode- en
    lidgegevensregels (#551/#681) gelden voor élke ingang en staan dus in die
    functie.
    """
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
            .join(
                MemberPerson,
                and_(
                    MemberPerson.member_id == Membership.member_id,
                    MemberPerson.relation_type == RelationType.PRIMARY_MEMBER,
                ),
            )
            .join(
                ContactDetail,
                and_(
                    ContactDetail.person_id == MemberPerson.person_id,
                    ContactDetail.contact_type_code == CONTACT.EMAIL,
                    func.lower(ContactDetail.value) == hoofdlid_email.lower(),
                ),
            )
            .filter(Membership.year == today.year)
            .all()
        )
        if existing_memberships:
            from app.domains.payment.api import PayableType, PaymentRecord, PaymentStatus

            for ms in existing_memberships:
                recs = (
                    db.query(PaymentRecord)
                    .filter(
                        PaymentRecord.payable_type == PayableType.MEMBERSHIP,
                        PaymentRecord.payable_id == ms.id,
                    )
                    .all()
                )
                if not recs or any(
                    r.status in (PaymentStatus.PAID, PaymentStatus.PENDING) for r in recs
                ):
                    raise HTTPException(
                        status_code=409,
                        detail=_(
                            "Er bestaat al een inschrijving voor %(year)s met dit e-mailadres. "
                            "Neem contact op met het bestuur als dit niet klopt."
                        )
                        % {"year": today.year},
                    )

    # CR-22 R9, Q28, Q40 (#1713): the rule is the service's; this door gives
    # its refusal a status.
    try:
        main_member = _service.main_member_for_sign_up(db, hoofdlid_email, signed_in)
    except KnownAddress as refusal:
        raise HTTPException(status_code=409, detail=str(refusal)) from refusal
    member, membership = _service.create_family_with_members(
        db,
        data,
        actor=PUBLIEKE_ACTOR,
        source="registration",
        today=today,
        main_member=main_member,
    )
    pc = db.query(PostalCode).filter(PostalCode.postal_code == data.postal_code).first()

    # Payment
    amount = membership_price_for_date(today)
    hoofdlid = data.members[0]
    description = (
        f"Raak Millegem lidmaatschap {today.year} – {hoofdlid.last_name} {hoofdlid.first_name}"
    )
    from app.kernel.tenant_config import tenant_base_url

    redirect_url = f"{tenant_base_url(db)}/betaling/succes?member={member.id}"

    try:
        # A call at the door, not an event handler (CR-13 phase 2, master CLI): an online payment
        # reaches the provider, the route needs the checkout URL now, and a failure rolls
        # the whole request back with a 502 — none of which a handler may do.
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

    # CR-13 phase 4: the welcome mail is an event, in this transaction — `mail`
    # queues it as a job, so it leaves after the commit and never for a
    # registration that was rolled back.
    if hoofdlid.email:
        publish(
            FamilyRegistered(
                member_id=member.id,
                to_email=hoofdlid.email,
                name=f"{hoofdlid.first_name} {hoofdlid.last_name}",
                municipality=pc.municipality if pc else "",
                payment_record_id=payment_record.id if payment_record is not None else None,
                form=data.model_dump(mode="json"),
            ),
            db,
        )

    db.commit()

    checkout_url = None
    if data.payment_method == PaymentMethod.ONLINE.value and payment_record.gateway_payment_id:
        from app.domains.payment.api import GatewayPayment

        gp = (
            db.query(GatewayPayment)
            .filter(GatewayPayment.id == payment_record.gateway_payment_id)
            .first()
        )
        if gp:
            checkout_url = gp.checkout_url

    status = (
        "pending_payment" if data.payment_method == PaymentMethod.ONLINE.value else "registered"
    )
    return FamilyRegisteredResponse(
        id=member.id, status=status, checkout_url=checkout_url, amount=amount
    )
