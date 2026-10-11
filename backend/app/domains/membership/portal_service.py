"""Lid-zelfbediening: het gezin bekijken, de e-mailadressen, de hernieuwing.

Een ingelogd lid kan:
- Het eigen gezin lezen (GET /member/household)
- De e-mailadressen van een gezinslid beheren (#1174)
- Het lidmaatschap hernieuwen

Een persoon bewerken, toevoegen of weghalen is sinds CR-13 fase 3 (#1250) van
`mdm` (de ene bewaring van het gezin, `mdm/household_save.py`): het gezin en zijn
personen zijn masterdata.

Elke schrijfactie logt een audit-rij (source="member_self", actor=e-mail).
De member_id wordt server-side afgeleid uit het JWT, nooit uit de request.

(verhuisd uit app/routers/member_household.py, #444)
"""

import logging
from datetime import date

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.domains.mdm.api import (
    CONTACT,
    Member,
    MemberPerson,
    household_of,
    household_refusals_as_http,
    person_payload,
)
from app.i18n import _

logger = logging.getLogger(__name__)

# The functions the facade calls for the portal (`api.py`). Until CR-13 phase 4c (#1251)
# this file was `household_router.py`; its JSON routes went in phase 4b, none had a caller,
# and a file that holds no route is not a router.


def _member_for(person, db: Session) -> Member:
    """Haal het gezin op voor de ingelogde persoon. 404 als er geen is."""
    with household_refusals_as_http():
        return household_of(db, person)


# No route of its own since CR-13 phase 4b (#1251): no caller. The facade (`api.py`) calls this
# function for the screen; it stays in this file until phase 4c moves it.
def main_person_of(db: Session, household_id: int):
    """The main member of the household with this id — whom a renewal runs for
    when the board starts it (#1899). None when the household has none; 404
    when there is no such household."""
    from app.domains.mdm.api import RelationType

    member = db.query(Member).filter(Member.id == household_id).first()
    if member is None:
        raise HTTPException(status_code=404, detail=_("Gezin niet gevonden"))
    return next(
        (
            link.person
            for link in member.member_persons
            if link.deleted_at is None
            and link.relation_type == RelationType.PRIMARY_MEMBER
            and link.person is not None
        ),
        None,
    )


def renewal_mail_address(db: Session, household_id: int) -> tuple[str, str] | None:
    """Where the confirmation of a renewal goes (#1903): the main member's
    confirmed e-mail address — the primary one first — with his name. None when
    the household has no main member, or he has no confirmed address: then no
    mail leaves, and the board's record says so."""
    main = main_person_of(db, household_id)
    if main is None:
        return None
    confirmed = sorted(
        (
            c
            for c in main.contact_details
            if c.contact_type_code == CONTACT.EMAIL and c.confirmed_at is not None and c.value
        ),
        key=lambda c: (not c.is_primary, c.id or 0),
    )
    if not confirmed:
        return None
    return confirmed[0].value, f"{main.first_name} {main.last_name}".strip()


def renew_membership(
    *,
    person,
    db: Session,
    payment_method: str = "online",
    by: str | None = None,
    return_path: str | None = None,
) -> dict:
    """Activeer/vernieuw het lidmaatschap van het eigen gezin via een online
    betaling (#113). Maakt géén nieuw gezin: het bestaande Member-record wordt
    hergebruikt. Een nieuw (nog niet-actief) Membership wordt aangemaakt; de
    Mollie-webhook activeert het bij betaling (zie handle_gateway_update).

    Weigert als er al een geldig lidmaatschap is — geen dubbele betaling.

    `by` is the board member who starts the renewal from the household's record
    (#1899): the history then names him and the board's source, where a member's
    own renewal names the member. `return_path` is where the provider sends the
    payer back — the household's record for the board, the payment page otherwise.
    """

    from app.domains.membership.api import Membership, has_valid_membership
    from app.domains.membership.history import snapshot_membership
    from app.domains.payment.api import create_payment_record

    member = _member_for(person, db)
    actor = by or next(
        (c.value for c in person.contact_details if c.contact_type_code == CONTACT.EMAIL), None
    )
    source = "admin_manual" if by else "member_self"

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
            source=source,
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
            source=source,
            actor=actor,
        )

    description = (
        f"Raak Millegem lidmaatschap {valid_to.year} – {person.last_name} {person.first_name}"
    )
    from app.kernel.tenant_config import tenant_base_url

    redirect_url = tenant_base_url(db) + (return_path or f"/betaling/succes?member={member.id}")
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
            audit_source=source,
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

    # #1903: the renewal is an order, and an order is confirmed by mail — to the
    # main member, whoever placed it. An event in this transaction: `mail` queues
    # the message, so it leaves after the commit and never for a renewal that
    # was rolled back.
    addressee = renewal_mail_address(db, member.id)
    if addressee is not None:
        from app.kernel.contracts.membership import MembershipRenewalPlaced
        from app.kernel.events import publish

        publish(
            MembershipRenewalPlaced(
                member_id=member.id,
                to_email=addressee[0],
                name=addressee[1],
                year=valid_to.year,
                valid_to=valid_to,
                amount=amount,
                payment_method=payment_method,
                payment_record_id=payment_record.id,
            ),
            db,
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


# No route of its own since CR-13 phase 4b (#1251): no caller. The facade (`api.py`) calls this
# function for the screen; it stays in this file until phase 4c moves it.
def get_household(*, person, db: Session) -> dict:
    return household_payload(_member_for(person, db))


def get_household_by_id(db: Session, household_id: int) -> dict:
    """The same view for the board's household record (#1899), which names the
    household and not a person of it. 404 when there is none."""
    member = db.query(Member).filter(Member.id == household_id).first()
    if member is None:
        raise HTTPException(status_code=404, detail=_("Gezin niet gevonden"))
    return household_payload(member)


def household_payload(member: Member) -> dict:
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
