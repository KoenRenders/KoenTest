"""Lid-zelfbediening: het gezin bekijken, de e-mailadressen, de hernieuwing.

Een ingelogd lid kan:
- Het eigen gezin lezen (GET /member/household)
- De e-mailadressen van een gezinslid beheren (#1174)
- Het lidmaatschap hernieuwen

Een persoon bewerken, toevoegen of weghalen is sinds CR-13 fase 3 (#1250) een deur
van `mdm` (`mdm/household_router.py`, dezelfde paden): het gezin en zijn personen
zijn masterdata.

Elke schrijfactie logt een audit-rij (source="member_self", actor=e-mail).
De member_id wordt server-side afgeleid uit het JWT, nooit uit de request.

(verhuisd uit app/routers/member_household.py, #444)
"""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.domains.auth.api import require_member
from app.domains.mdm.api import (
    CONTACT,
    Member,
    MemberPerson,
    Person,
    household_of,
    household_person,
    household_refusals_as_http,
    person_payload,
)
from app.i18n import _

logger = logging.getLogger(__name__)

router = APIRouter(tags=["member-self"])


def _member_for(person, db: Session) -> Member:
    """Haal het gezin op voor de ingelogde persoon. 404 als er geen is."""
    with household_refusals_as_http():
        return household_of(db, person)


@router.post("/member/household/renew-membership")
def renew_membership(
    person=Depends(require_member), db: Session = Depends(get_db), payment_method: str = "online"
):
    """Activeer/vernieuw het lidmaatschap van het eigen gezin via een online
    betaling (#113). Maakt géén nieuw gezin: het bestaande Member-record wordt
    hergebruikt. Een nieuw (nog niet-actief) Membership wordt aangemaakt; de
    Mollie-webhook activeert het bij betaling (zie handle_gateway_update).

    Weigert als er al een geldig lidmaatschap is — geen dubbele betaling.
    """

    from app.domains.audit.api import snapshot_membership
    from app.domains.membership.api import Membership, has_valid_membership
    from app.domains.payment.api import create_payment_record

    member = _member_for(person, db)
    actor = next(
        (c.value for c in person.contact_details if c.contact_type_code == CONTACT.EMAIL), None
    )

    today = date.today()

    # Controleer of de hernieuwingscampagne open is.
    # Hernieuwingsvenster-regel op één plek (§19.3): membership-facade.
    from app.domains.membership.api import renewal_open as _renewal_open

    renewal_window_open = _renewal_open(today)

    # The period and the price: one rule, shared with the page that announces
    # them before the click (#1590) — `membership.service.renewal_terms`.
    from app.domains.membership.api import renewal_terms

    valid_from, valid_to, amount = renewal_terms(db, person, today)

    if has_valid_membership(person) and not renewal_window_open:
        raise HTTPException(status_code=409, detail=_("Je hebt al een geldig lidmaatschap."))

    # Blokkeer een dubbele vernieuwingsprocedure als er al een niet-betaalde/
    # niet-geannuleerde PaymentRecord voor dit lid bestaat. Dezelfde functie voedt
    # het gezinsportaal (#618), zodat scherm en guard het altijd eens zijn.
    from app.domains.membership.api import open_renewal_payment

    if open_renewal_payment(db, member):
        raise HTTPException(
            status_code=409,
            detail=_("Je betaling loopt nog — rond eerst de openstaande betaling af."),
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
            detail=_("Je hebt je lidmaatschap voor %(year)s al vernieuwd.")
            % {"year": valid_to.year},
        )
    if membership:
        membership.valid_from = valid_from
        membership.valid_to = valid_to
        db.flush()
        snapshot_membership(
            db,
            membership,
            operation="update",
            action="membership_renewal_started",
            source="member_self",
            actor=actor,
        )
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
        snapshot_membership(
            db,
            membership,
            operation="insert",
            action="membership_renewal_started",
            source="member_self",
            actor=actor,
        )

    description = (
        f"Raak Millegem lidmaatschap {valid_to.year} – {person.last_name} {person.first_name}"
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

            gp = (
                db.query(GatewayPayment)
                .filter(GatewayPayment.id == payment_record.gateway_payment_id)
                .first()
            )
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
    # One order for the JSON and the portal page (Koen, 29 September 2026): the
    # household's own, not the order the database happens to return the rows in.
    links = sorted(member.member_persons, key=MemberPerson.household_position)
    persons = [mp.person for mp in links]
    board_person = None
    if member.board_member_id:
        board_person = next((p for p in persons if p.id == member.board_member_id), None)
    return {
        "member_id": member.id,
        "board_member_id": member.board_member_id,
        "board_member_name": (
            f"{board_person.first_name} {board_person.last_name}".strip() if board_person else None
        ),
        "persons": [person_payload(mp.person) for mp in links],
    }


# ── E-mailadressen van een gezinslid (#1174) ─────────────────────────────────
#
# Ook door het LID zelf, niet alleen door het bestuur. Koen, 27 september 2026:
# *"Wat mij betreft kan een lid dat zelfs in het publieke deel bepalen, dan zien
# we dat ook in de wijzigingen."* De lus die dat sluit bestaat al — portaal →
# auditlogboek → de .ods-export van de ledenwijzigingen → met de hand overtypen
# in het Raak Nationaal-programma.
#
# Dezelfde gezinsgrens als elke andere portaalbewerking: `mdm.api.household_person`.
# Zonder die controle kon een lid met een persoon-id van iemand anders diens
# adressen beheren.


def _household_target(person, person_id: int, db: Session) -> Person:
    member = _member_for(person, db)
    with household_refusals_as_http():
        return household_person(db, member, person_id)


def _actor_van(person) -> str | None:
    return next(
        (c.value for c in person.contact_details if c.contact_type_code == CONTACT.EMAIL), None
    )


def household_add_email(
    person_id: int, data: dict, person=Depends(require_member), db: Session = Depends(get_db)
):
    from app.domains.mdm.api import add_email_address

    _household_target(person, person_id, db)
    # CR-22 R15 (#1711): the member adds it himself, so it waits for its code.
    add_email_address(
        db, person_id, (data or {}).get("email") or "", actor=_actor_van(person), confirmed=False
    )
    return {"ok": True}


def household_apply_email_rows(
    person_id: int, formulier, person=Depends(require_member), db: Session = Depends(get_db)
):
    """De e-mailrijen uit het portaalformulier toepassen (#1219).

    Dezelfde gezinsgrens als elke andere portaalbewerking: zonder
    `household_person` kon een lid met het persoon-id van een vreemde diens
    adressen bewerken.
    """
    from app.domains.mdm.api import apply_email_rows

    _household_target(person, person_id, db)
    apply_email_rows(db, person_id, formulier, actor=_actor_van(person), confirmed=False)
    return {"ok": True}


def household_make_email_primary(
    person_id: int, contact_id: int, person=Depends(require_member), db: Session = Depends(get_db)
):
    from app.domains.mdm.api import make_email_primary

    _household_target(person, person_id, db)
    make_email_primary(db, person_id, contact_id, actor=_actor_van(person))
    return {"ok": True}


def household_remove_email(
    person_id: int, contact_id: int, person=Depends(require_member), db: Session = Depends(get_db)
):
    from app.domains.mdm.api import remove_email_address

    _household_target(person, person_id, db)
    remove_email_address(db, person_id, contact_id, actor=_actor_van(person))
    return None
