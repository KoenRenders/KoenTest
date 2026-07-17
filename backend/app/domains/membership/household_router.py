"""Lid-zelfbediening: gezin bekijken en bewerken.

Een ingelogd lid kan:
- Het eigen gezin lezen (GET /member/household)
- Persoonsgegevens, adres en contactgegevens aanpassen per persoon
- Personen aan het gezin toevoegen of verwijderen

NIET bewerkbaar via deze endpoints (server-side genegeerd of geblokkeerd):
- Member.board_member_id  (verantwoordelijk lid: alleen admin)
- ExternalNumber           (extern ledenummer: alleen admin)
- MemberPerson.relation_type (type: alleen admin)

Elke schrijfactie logt een audit-rij (source="member_self", actor=e-mail).
De member_id wordt server-side afgeleid uit het JWT, nooit uit de request.

(verhuisd uit app/routers/member_household.py, #444)
"""
import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.domains.auth.api import require_member
from app.database import get_db
from app.domains.mdm.api import Member, Person, MemberPerson
from app.domains.mdm.api import ContactDetail
from app.domains.mdm.api import PostalCode
from app.domains.audit.api import (
    snapshot_person,
    snapshot_member_person,
    snapshot_address,
    snapshot_contact_detail,
)
from app.soft_delete import soft_delete
from app.i18n import _

logger = logging.getLogger(__name__)

router = APIRouter(tags=["member-self"])


def _member_for(person, db: Session) -> Member:
    """Haal het gezin op voor de ingelogde persoon. 404 als er geen is."""
    mp = next((m for m in person.member_persons), None)
    if not mp:
        raise HTTPException(status_code=404, detail=_("Geen gezin gevonden."))
    return db.query(Member).filter(Member.id == mp.member_id).first()


def _assert_in_household(person, member):
    """403 als de persoon niet tot dit gezin behoort."""
    if not any(mp.member_id == member.id for mp in person.member_persons):
        raise HTTPException(status_code=403, detail=_("Geen toegang tot dit gezin."))


def _person_payload(p: Person):
    mp = next((m for m in p.member_persons), None)
    contacts = {c.contact_type_code: c.value for c in p.contact_details}
    address = None
    if p.address:
        a = p.address
        pc = a.postal_code
        address = {
            "id": a.id,
            "street": a.street,
            "house_number": a.house_number,
            "bus_number": a.bus_number,
            "postal_code": pc.postal_code if pc else None,
            "municipality": pc.municipality if pc else None,
            "postal_code_id": a.postal_code_id,
        }
    return {
        "id": p.id,
        "first_name": p.first_name,
        "last_name": p.last_name,
        "date_of_birth": p.date_of_birth.isoformat() if p.date_of_birth else None,
        "gender_code": p.gender_code,
        "relation_type": mp.relation_type if mp else None,
        "address": address,
        "email": contacts.get("EMAIL"),
        "phone": contacts.get("PHONE"),
        "mobile": contacts.get("MOBILE"),
    }


@router.post("/member/household/renew-membership")
def renew_membership(person=Depends(require_member), db: Session = Depends(get_db),
                     payment_method: str = "online"):
    """Activeer/vernieuw het lidmaatschap van het eigen gezin via een online
    betaling (#113). Maakt géén nieuw gezin: het bestaande Member-record wordt
    hergebruikt. Een nieuw (nog niet-actief) Membership wordt aangemaakt; de
    Mollie-webhook activeert het bij betaling (zie handle_gateway_update).

    Weigert als er al een geldig lidmaatschap is — geen dubbele betaling.
    """
    from datetime import date

    from app.domains.membership.api import Membership
    from app.domains.payment.api import (
        membership_price_for_date,
        membership_valid_period,
        create_payment_record,
    )
    from app.domains.audit.api import snapshot_membership
    from app.config import settings
    from app.domains.membership.api import has_valid_membership, membership_coverage_until

    member = _member_for(person, db)
    actor = next((c.value for c in person.contact_details if c.contact_type_code == "EMAIL"), None)

    today = date.today()

    # Controleer of de hernieuwingscampagne open is.
    # Hernieuwingsvenster-regel op één plek (§19.3): membership-facade.
    from app.domains.membership.api import renewal_open as _renewal_open
    renewal_window_open = _renewal_open(today)

    # Doeljaar van de hernieuwing. Heeft het lid al een geldig lidmaatschap, dan
    # dekt de hernieuwing het jaar ná de huidige geldigheid — anders zouden we het
    # lopende jaar dupliceren (uq_memberships_member_year). Geen geldig lidmaatschap
    # (verlopen): val terug op de normale periode-regel (huidig of volgend jaar).
    # Dekking t/m incl. een al betaald volgend jaar (#496): mik op het jaar ná de
    # verste dekking, zodat een al vernieuwd jaar niet op een 409 botst.
    current_until = membership_coverage_until(person, today)
    if current_until is not None:
        ny = current_until.year + 1
        valid_from, valid_to = date(ny, 1, 1), date(ny, 12, 31)
    else:
        valid_from, valid_to = membership_valid_period(today)

    # Prijs: een hernieuwing voor een vol kalenderjaar (valid_from = 1 jan) kost
    # altijd de volle prijs. De halve prijs geldt enkel voor een (her)instap mid-jaar
    # voor de rest van het lopende jaar — dus enkel in de verlopen-fallback hierboven.
    is_full_year = (valid_from.month, valid_from.day) == (1, 1)
    from app.kernel.tenant_config import tenant_membership_config

    amount = (tenant_membership_config(db)["price_full"] if is_full_year
              else membership_price_for_date(today))

    if has_valid_membership(person) and not renewal_window_open:
        raise HTTPException(status_code=409, detail=_("Je hebt al een geldig lidmaatschap."))

    # Blokkeer een dubbele vernieuwingsprocedure als er al een niet-betaalde/
    # niet-geannuleerde PaymentRecord voor dit lid bestaat.
    from app.domains.payment.api import PaymentRecord as PR
    existing_pending = (
        db.query(PR)
        .filter(PR.payable_type == "membership", PR.status.notin_(["paid", "cancelled", "failed"]))
        .join(Membership, Membership.id == PR.payable_id)
        .filter(Membership.member_id == member.id)
        .first()
    )
    if existing_pending:
        raise HTTPException(
            status_code=409,
            detail=_("Je vernieuwing loopt nog — rond eerst de openstaande betaling af."),
        )

    # Hergebruik een bestaand (niet-actief) lidmaatschap voor het doeljaar i.p.v.
    # een tweede rij in te voegen — voorkomt uq_memberships_member_year bij een
    # herpoging na een geannuleerde/mislukte betaling.
    membership = (
        db.query(Membership)
        .filter(Membership.member_id == member.id, Membership.year == valid_to.year)
        .first()
    )
    if membership and membership.is_active:
        raise HTTPException(
            status_code=409,
            detail=_("Je hebt je lidmaatschap voor %(year)s al vernieuwd.") % {"year": valid_to.year},
        )
    if membership:
        membership.valid_from = valid_from
        membership.valid_to = valid_to
        db.flush()
        snapshot_membership(db, membership, operation="update", action="membership_renewal_started",
                            source="member_self", actor=actor)
    else:
        membership = Membership(
            member_id=member.id,
            year=valid_to.year,
            is_active=False,
            valid_from=valid_from,
            valid_to=valid_to,
        )
        db.add(membership)
        db.flush()
        snapshot_membership(db, membership, operation="insert", action="membership_renewal_started",
                            source="member_self", actor=actor)

    description = f"Raak Millegem lidmaatschap {valid_to.year} – {person.last_name} {person.first_name}"
    from app.kernel.tenant_config import tenant_base_url

    redirect_url = f"{tenant_base_url(db)}/betaling/succes?member={member.id}"
    try:
        payment_record = create_payment_record(
            db=db,
            payable_type="membership",
            payable_id=membership.id,
            amount=amount,
            method=payment_method,
            redirect_url=redirect_url,
            description=description,
            audit_source="member_self",
            audit_actor=actor,
        )
    except ValueError as e:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(e))

    checkout_url = None
    if payment_method == "online":
        if payment_record.gateway_payment_id:
            from app.domains.payment.api import GatewayPayment
            gp = db.query(GatewayPayment).filter(GatewayPayment.id == payment_record.gateway_payment_id).first()
            if gp:
                checkout_url = gp.checkout_url
        # Online betaling zonder checkout-URL is onbruikbaar — niet bewaren.
        if not checkout_url:
            db.rollback()
            raise HTTPException(
                status_code=502,
                detail=_("De online betaling kon niet gestart worden. Probeer het later opnieuw."),
            )

    # Bij overschrijving (#497): geen checkout; de OGM staat op het record en de
    # instructies worden op het gezinsportaal getoond.
    db.commit()
    return {
        "checkout_url": checkout_url,
        "amount": str(amount),
        "payment_method": payment_method,
        "structured_communication": payment_record.structured_communication,
    }


@router.get("/member/household")
def get_household(person=Depends(require_member), db: Session = Depends(get_db)):
    member = _member_for(person, db)
    persons = [mp.person for mp in member.member_persons]
    board_person = None
    if member.board_member_id:
        board_person = next((p for p in persons if p.id == member.board_member_id), None)
    return {
        "member_id": member.id,
        "board_member_id": member.board_member_id,
        "board_member_name": (
            f"{board_person.first_name} {board_person.last_name}".strip() if board_person else None
        ),
        "persons": [_person_payload(mp.person) for mp in member.member_persons],
    }


@router.put("/member/household/persons/{person_id}")
def update_person(
    person_id: int,
    data: dict,
    person=Depends(require_member),
    db: Session = Depends(get_db),
):
    member = _member_for(person, db)
    target = db.query(Person).filter(Person.id == person_id).first()
    if not target:
        raise HTTPException(status_code=404, detail=_("Persoon niet gevonden."))
    _assert_in_household(target, member)

    # Enkel toegestane velden; relation_type, board_member_id, ExternalNumber
    # worden nooit aangeraakt.
    actor = next((c.value for c in person.contact_details if c.contact_type_code == "EMAIL"), None)
    changed = False
    for field in ("first_name", "last_name", "date_of_birth", "gender_code"):
        if field not in data:
            continue
        new_val = data[field] or None
        if field == "date_of_birth" and new_val is not None and not isinstance(new_val, date):
            new_val = date.fromisoformat(new_val)
        # Enkel snapshotten wat écht wijzigt (#188): een formulier stuurt alle velden,
        # maar een onveranderd veld hoort geen history-rij te maken.
        if getattr(target, field) != new_val:
            setattr(target, field, new_val)
            changed = True
    if changed:
        snapshot_person(db, target, operation="update", action="person_updated",
                        source="member_self", actor=actor)

    # Adres
    if "address" in data and data["address"] and target.address:
        a = target.address
        adat = data["address"]
        addr_changed = False
        for field in ("street", "house_number"):
            if field in adat and adat[field] is not None:
                setattr(a, field, adat[field])
                addr_changed = True
        if "bus_number" in adat:
            a.bus_number = adat["bus_number"] or None
            addr_changed = True
        if "postal_code" in adat and adat["postal_code"]:
            pc = db.query(PostalCode).filter(PostalCode.postal_code == adat["postal_code"]).first()
            if not pc:
                raise HTTPException(status_code=422, detail=_("Onbekende postcode: %(postal_code)s") % {"postal_code": adat['postal_code']})
            a.postal_code_id = pc.id
            addr_changed = True
        if addr_changed:
            snapshot_address(db, a, operation="update", action="address_updated",
                             source="member_self", actor=actor)

    # Contactgegevens
    def _upsert(type_code: str, value: Optional[str]):
        existing = next((c for c in target.contact_details if c.contact_type_code == type_code), None)
        if value:
            if existing:
                if existing.value != value:
                    existing.value = value
                    db.flush()
                    snapshot_contact_detail(db, existing, operation="update", action="contacts_updated",
                                            source="member_self", actor=actor)
            else:
                contact = ContactDetail(person_id=target.id, contact_type_code=type_code,
                                        value=value, is_primary=True)
                target.contact_details.append(contact)
                db.flush()
                snapshot_contact_detail(db, contact, operation="insert", action="contacts_updated",
                                        source="member_self", actor=actor)
        elif existing:
            snapshot_contact_detail(db, existing, operation="delete", action="contacts_updated",
                                    source="member_self", actor=actor)
            target.contact_details.remove(existing)

    if "email" in data:
        _upsert("EMAIL", data["email"])
    if "phone" in data:
        _upsert("PHONE", data["phone"])
    if "mobile" in data:
        _upsert("MOBILE", data["mobile"])

    db.commit()
    db.refresh(target)
    return _person_payload(target)


@router.post("/member/household/persons", status_code=201)
def add_person(
    data: dict,
    person=Depends(require_member),
    db: Session = Depends(get_db),
):
    member = _member_for(person, db)
    actor = next((c.value for c in person.contact_details if c.contact_type_code == "EMAIL"), None)

    first_name = (data.get("first_name") or "").strip()
    last_name = (data.get("last_name") or "").strip()
    if not first_name or not last_name:
        raise HTTPException(status_code=422, detail=_("Voornaam en achternaam zijn verplicht."))

    new_person = Person(
        first_name=first_name,
        last_name=last_name,
        date_of_birth=data.get("date_of_birth") or None,
        gender_code=data.get("gender_code") or None,
    )
    db.add(new_person)
    db.flush()
    snapshot_person(db, new_person, operation="insert", action="person_created",
                    source="member_self", actor=actor)

    # Relatietype wordt altijd door het systeem bepaald, nooit door het lid.
    mp = MemberPerson(member_id=member.id, person_id=new_person.id, relation_type="KIND")
    db.add(mp)
    db.flush()
    snapshot_member_person(db, mp, operation="insert", action="person_added_to_family",
                           source="member_self", actor=actor)

    # Geen adres voor extra gezinsleden: het adres hoort enkel bij het hoofdlid (#125).

    for type_code, key in [("EMAIL", "email"), ("PHONE", "phone"), ("MOBILE", "mobile")]:
        if data.get(key):
            contact = ContactDetail(person_id=new_person.id, contact_type_code=type_code,
                                    value=data[key], is_primary=True)
            db.add(contact)
            db.flush()
            snapshot_contact_detail(db, contact, operation="insert", action="contacts_updated",
                                    source="member_self", actor=actor)

    db.commit()
    db.refresh(new_person)
    return _person_payload(new_person)


@router.delete("/member/household/persons/{person_id}", status_code=204)
def remove_person(
    person_id: int,
    person=Depends(require_member),
    db: Session = Depends(get_db),
):
    member = _member_for(person, db)
    target = db.query(Person).filter(Person.id == person_id).first()
    if not target:
        raise HTTPException(status_code=404, detail=_("Persoon niet gevonden."))
    _assert_in_household(target, member)

    # Een lid mag zichzelf niet uit het gezin verwijderen.
    if target.id == person.id:
        raise HTTPException(status_code=400, detail=_("Je kan jezelf niet uit het gezin verwijderen."))

    actor = next((c.value for c in person.contact_details if c.contact_type_code == "EMAIL"), None)

    mp = next((m for m in target.member_persons if m.member_id == member.id), None)
    if mp:
        snapshot_member_person(db, mp, operation="delete", action="person_removed_from_family",
                               source="member_self", actor=actor)
        soft_delete(mp)

    db.commit()
