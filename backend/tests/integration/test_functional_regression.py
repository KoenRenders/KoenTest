"""Functionele regressietests op de kern-flows: registratie, audit-trail,
webhook-idempotentie en de gedeelde totaalberekening."""

from decimal import Decimal

from app.domains.payment.api import PayableType, PaymentStatus
from tests import payments_door
from tests.conftest import (
    register_at_the_door,
    seed_activity_with_product,
    seed_postal_code,
    sign_up_at_the_door,
)


def _family_payload(email="happy@example.com"):
    return {
        "street": "Milostraat",
        "house_number": "40",
        "postal_code": "2400",
        "payment_method": "transfer",
        "members": [
            {
                "last_name": "Peeters",
                "first_name": "Jan",
                "email": email,
                "mobile": "0470000000",
                "date_of_birth": "1980-01-01",
                "gender_code": "M",
                "relation_type": "HOOFDLID",
            },
            {
                "last_name": "Peeters",
                "first_name": "Kind",
                "relation_type": "KIND",
                # #551: bijkomend lid vereist geboortedatum + geslacht.
                "date_of_birth": "2012-03-04",
                "gender_code": "M",
            },
        ],
    }


def test_family_registration_happy_path_writes_data_and_audit(client, db_session):
    seed_postal_code(db_session)
    resp = sign_up_at_the_door(client, json=_family_payload())
    assert resp.status_code == 201, resp.text

    from app.domains.mdm.api import Member, MemberHistory, Person
    from app.domains.membership.api import Membership
    from app.domains.payment.api import PaymentRecord, PaymentRecordHistory

    assert db_session.query(Member).count() == 1
    assert db_session.query(Person).count() == 2
    assert db_session.query(Membership).count() == 1
    assert (
        db_session.query(PaymentRecord)
        .filter(PaymentRecord.payable_type == PayableType.MEMBERSHIP)
        .count()
        == 1
    )

    # Audit-trail meegeschreven met de juiste bron/actie.
    mh = db_session.query(MemberHistory).filter(MemberHistory.action == "family_registered").first()
    assert mh is not None and mh.source == "registration" and mh.operation == "insert"
    ph = (
        db_session.query(PaymentRecordHistory)
        .filter(PaymentRecordHistory.action == "payment_created")
        .first()
    )
    assert ph is not None and ph.source == "registration"


def test_payment_overview_membership_shows_family_and_year(client, db_session):
    """Het betaaloverzicht verrijkt een lidmaatschapsbetaling met het gezin
    (hoofdlid-naam) en het jaar — payable_id is de Membership.id, niet de Member.id (#141)."""
    seed_postal_code(db_session)
    assert (
        sign_up_at_the_door(client, json=_family_payload(email="overview@example.com")).status_code
        == 201
    )

    from app.domains.membership.api import Membership

    ms = db_session.query(Membership).first()

    resp = payments_door.records(client)
    assert resp.status_code == 200, resp.text
    rec = next(r for r in resp.json() if r["payable_type"] == "membership")
    assert rec["description"] == f"Lidmaatschap {ms.year}"
    assert rec["contact_name"] == "Jan Peeters"  # hoofdlid uit _family_payload
    # Gestructureerd lidgeld-jaar voedt de jaarfilter op de betalingenpagina (#308).
    assert rec["membership_year"] == ms.year


def test_family_registration_requires_hoofdlid_contact(client, db_session):
    seed_postal_code(db_session)
    payload = _family_payload()
    payload["members"][0]["email"] = None  # hoofdlid zonder e-mail
    resp = sign_up_at_the_door(client, json=payload)
    assert resp.status_code == 422


def test_manual_confirm_writes_audit_with_actor(client, db_session):
    seed_postal_code(db_session)
    sign_up_at_the_door(client, json=_family_payload(email="confirm@example.com"))
    from app.domains.payment.api import PaymentRecord

    rec = db_session.query(PaymentRecord).first()

    resp = payments_door.update(client, rec.id, {"status": "paid"})
    assert resp.status_code == 200, resp.text

    from app.domains.payment.api import PaymentRecordHistory

    h = (
        db_session.query(PaymentRecordHistory)
        .filter(PaymentRecordHistory.action == "payment_manually_confirmed")
        .first()
    )
    assert h is not None
    assert h.source == "admin_manual"
    assert h.actor == "beheerder@example.com"
    assert h.status == PaymentStatus.PAID.value  # history: kale string (§F4)


def test_webhook_update_idempotent_no_double_credit(client, db_session):
    """Twee keer dezelfde 'paid'-update mag het betaalde bedrag niet verdubbelen
    en logt maar één status-transitie."""
    from app.domains.payment.api import (
        GatewayPayment,
        PaymentRecord,
        PaymentRecordHistory,
        handle_gateway_update,
    )

    gp = GatewayPayment(
        provider="mollie",
        provider_payment_id="tr_idem",
        amount=Decimal("35.00"),
        status="pending",
        payment_metadata={},
    )
    db_session.add(gp)
    db_session.flush()
    rec = PaymentRecord(
        payable_type="membership",
        payable_id=1,
        amount=Decimal("35.00"),
        method="online",
        status="pending",
        gateway_payment_id=gp.id,
    )
    db_session.add(rec)
    db_session.flush()

    handle_gateway_update(db_session, gateway_payment_id=gp.id, new_status="paid")
    handle_gateway_update(db_session, gateway_payment_id=gp.id, new_status="paid")
    db_session.flush()

    assert rec.status == PaymentStatus.PAID
    assert rec.amount_paid == Decimal("35.00")  # toegekend, niet opgeteld
    transitions = (
        db_session.query(PaymentRecordHistory)
        .filter(
            PaymentRecordHistory.payment_record_id == rec.id,
            PaymentRecordHistory.action == "payment_paid",
        )
        .count()
    )
    assert transitions == 1


def test_cms_placeholders_public_vs_editor(client, db_session):
    """Publiek worden de prijscodes ingevuld vanuit config; de editor (admin)
    krijgt de ruwe codes zodat ze bewerkbaar blijven.

    Sinds golf 11 (migratie 141, #913) bevat de STANDAARD-introtekst geen
    prijscodes meer — het tarief komt uit de betaal-api in de introband. Het
    placeholder-mechanisme zelf blijft bestaan voor redacteurs die de codes
    typen, dus de test zaait zijn eigen tekst mét code in plaats van op de
    standaardtekst te leunen."""
    import sqlalchemy as sa

    db_session.execute(
        sa.text("UPDATE cms.cms_pages SET content = :c WHERE slug = 'home-intro'").bindparams(
            c="<p>Lidgeld: {{membership_price_full}} per gezin.</p>"
        )
    )
    db_session.commit()

    # The public side: the home page shows the block with its code filled in.
    # (Until CR-13 phase 4b this asked the JSON route of the block.)
    public = client.get("/")
    assert public.status_code == 200
    assert "{{membership_price_full}}" not in public.text  # code vervangen
    assert (
        "Lidgeld: €35,00 per gezin." in public.text or "Lidgeld: €17,50 per gezin." in public.text
    )

    # The back office's side: the page as it is stored keeps the raw code.
    from app.domains.cms.api import list_pages

    db_session.expire_all()
    home = next(p for p in list_pages(db_session) if p.slug == "home-intro")
    assert "{{membership_price_full}}" in home.content  # ruwe code blijft


def test_admin_creates_paid_activity_and_public_registration(client, db_session):
    """End-to-end: het bestuur maakt op de fiche een activiteit en bewaart er een
    onderdeel met een betaald product bij; een bezoeker schrijft zich publiek in
    via overschrijving; het betaalrecord-bedrag is gelijk aan de productprijs.
    (Tot CR-13 fase 4b, #1251, via de JSON-routes die niemand anders aanriep.)"""
    from app.domains.activities.api import Activity
    from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
    from tests._fiche import Fiche, post_new_activity
    from tests.conftest import SEEDED_ADMIN_EMAIL

    session = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, session)
    board = {"X-CSRF-Token": csrf_token_for(session)}
    created = post_new_activity(
        client,
        board,
        {
            "name": "Flowtest betaalde activiteit",
            "start_date": "2099-12-31",
            "location": "Teststraat",
        },
    )
    assert created.status_code == 200, created.text[:300]
    activity = db_session.query(Activity).filter_by(name="Flowtest betaalde activiteit").one()
    activity_id = activity.id
    fiche = Fiche(db_session, activity_id)
    row = fiche.add("c", name="Flowtest onderdeel")
    fiche.add("p", parent=row, name="Flowtest product", price="7,50")
    assert fiche.post(client, board).status_code == 200
    # A new activity is a draft; registering opens when the board publishes it.
    published = client.post(
        f"/admin/activiteiten/{activity_id}/status", data={"status": "published"}, headers=board
    )
    assert published.status_code in (200, 204), published.text[:300]
    client.cookies.clear()
    db_session.expire_all()
    component = activity.sub_registrations[0]
    component_id, product_id = component.id, component.products[0].id

    reg = register_at_the_door(
        client,
        activity_id,
        json={
            "contact_name": "Flow Inschrijver",
            "phone": "0470000000",
            "contact_email": "flow+act@example.com",
            "payment_method": "transfer",
            "component_id": component_id,
            "items": [{"product_id": product_id, "quantity": 1}],
        },
    )
    assert reg.status_code == 200, reg.text

    from app.domains.payment.api import PaymentRecord

    rec = (
        db_session.query(PaymentRecord)
        .filter(PaymentRecord.payable_type == PayableType.REGISTRATION)
        .first()
    )
    assert rec is not None
    assert rec.amount == Decimal("7.50")


def test_registration_total_matches_payment_amount(client, db_session, mock_mollie):
    """De gedeelde totaalberekening voedt zowel het bedrag richting Mollie als de
    bevestiging; ze moeten gelijk zijn."""
    _, comp, product = seed_activity_with_product(db_session, price="12.50")
    activity_id = comp.activity_id

    resp = register_at_the_door(
        client,
        activity_id,
        json={
            "contact_name": "Test",
            "phone": "0470000000",
            "contact_email": "total@example.com",
            "payment_method": "online",
            "component_id": comp.id,
            "items": [{"product_id": product.id, "quantity": 3}],
        },
    )
    assert resp.status_code == 200, resp.text

    from app.domains.activities.api import Registration, compute_registration_total
    from app.domains.payment.api import PaymentRecord

    rec = (
        db_session.query(PaymentRecord)
        .filter(PaymentRecord.payable_type == PayableType.REGISTRATION)
        .first()
    )
    reg = db_session.query(Registration).first()
    total, _lines = compute_registration_total(reg)
    assert total == Decimal("37.50")  # 3 × 12.50
    assert rec.amount == total
