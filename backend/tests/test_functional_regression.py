"""Functionele regressietests op de kern-flows: registratie, audit-trail,
webhook-idempotentie en de gedeelde totaalberekening."""
from decimal import Decimal

from tests.conftest import seed_postal_code, seed_activity_with_product


def _family_payload(email="happy@example.com"):
    return {
        "street": "Milostraat", "house_number": "40", "postal_code": "2400",
        "payment_method": "transfer",
        "members": [
            {"last_name": "Peeters", "first_name": "Jan", "email": email,
             "mobile": "0470000000", "relation_type": "HOOFDLID"},
            {"last_name": "Peeters", "first_name": "Kind", "relation_type": "KIND"},
        ],
    }


def test_family_registration_happy_path_writes_data_and_audit(client, db_session):
    seed_postal_code(db_session)
    resp = client.post("/api/v1/families", json=_family_payload())
    assert resp.status_code == 201, resp.text

    from app.models.member import Member, Person, Membership
    from app.domains.payment_status.models import PaymentRecord
    from app.models.history import MemberHistory, PaymentRecordHistory

    assert db_session.query(Member).count() == 1
    assert db_session.query(Person).count() == 2
    assert db_session.query(Membership).count() == 1
    assert db_session.query(PaymentRecord).filter(PaymentRecord.payable_type == "membership").count() == 1

    # Audit-trail meegeschreven met de juiste bron/actie.
    mh = db_session.query(MemberHistory).filter(MemberHistory.action == "family_registered").first()
    assert mh is not None and mh.source == "registration" and mh.operation == "insert"
    ph = db_session.query(PaymentRecordHistory).filter(PaymentRecordHistory.action == "payment_created").first()
    assert ph is not None and ph.source == "registration"


def test_family_registration_requires_hoofdlid_contact(client, db_session):
    seed_postal_code(db_session)
    payload = _family_payload()
    payload["members"][0]["email"] = None  # hoofdlid zonder e-mail
    resp = client.post("/api/v1/families", json=payload)
    assert resp.status_code == 422


def test_manual_confirm_writes_audit_with_actor(client, db_session, admin_headers):
    seed_postal_code(db_session)
    client.post("/api/v1/families", json=_family_payload(email="confirm@example.com"))
    from app.domains.payment_status.models import PaymentRecord
    rec = db_session.query(PaymentRecord).first()

    resp = client.patch(
        f"/api/v1/payment-status/records/{rec.id}",
        json={"status": "paid"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text

    from app.models.history import PaymentRecordHistory
    h = db_session.query(PaymentRecordHistory).filter(
        PaymentRecordHistory.action == "payment_manually_confirmed"
    ).first()
    assert h is not None
    assert h.source == "admin_manual"
    assert h.actor == "koen.renders@gmail.com"
    assert h.status == "paid"


def test_webhook_update_idempotent_no_double_credit(client, db_session):
    """Twee keer dezelfde 'paid'-update mag het betaalde bedrag niet verdubbelen
    en logt maar één status-transitie."""
    from app.domains.payment_gateway.models import GatewayPayment
    from app.domains.payment_status.models import PaymentRecord
    from app.domains.payment_status.service import handle_gateway_update
    from app.models.history import PaymentRecordHistory

    gp = GatewayPayment(provider="mollie", provider_payment_id="tr_idem",
                        amount=Decimal("35.00"), status="pending", payment_metadata={})
    db_session.add(gp)
    db_session.flush()
    rec = PaymentRecord(payable_type="membership", payable_id=1, amount=Decimal("35.00"),
                        method="online", status="pending", gateway_payment_id=gp.id)
    db_session.add(rec)
    db_session.flush()

    handle_gateway_update(db_session, gateway_payment_id=gp.id, new_status="paid")
    handle_gateway_update(db_session, gateway_payment_id=gp.id, new_status="paid")
    db_session.flush()

    assert rec.status == "paid"
    assert rec.amount_paid == Decimal("35.00")  # toegekend, niet opgeteld
    transitions = db_session.query(PaymentRecordHistory).filter(
        PaymentRecordHistory.payment_record_id == rec.id,
        PaymentRecordHistory.action == "payment_paid",
    ).count()
    assert transitions == 1


def test_cms_placeholders_public_vs_editor(client, admin_headers):
    """Publiek wordt de home-intro ingevuld vanuit config; de editor (admin)
    krijgt de ruwe codes zodat ze bewerkbaar blijven."""
    public = client.get("/api/v1/blocks/home-intro")
    assert public.status_code == 200
    content = public.json()["content"]
    assert "{{" not in content              # codes vervangen
    assert "€35,00" in content or "€17,50" in content

    admin = client.get("/api/v1/admin/pages", headers=admin_headers)
    assert admin.status_code == 200
    home = next(p for p in admin.json() if p["slug"] == "home-intro")
    assert "{{membership_price_full}}" in home["content"]   # ruwe code blijft


def test_registration_total_matches_payment_amount(client, db_session, mock_mollie):
    """De gedeelde totaalberekening voedt zowel het bedrag richting Mollie als de
    bevestiging; ze moeten gelijk zijn."""
    _, comp, product = seed_activity_with_product(db_session, price="12.50")
    activity_id = comp.activity_id

    resp = client.post(f"/api/v1/activities/{activity_id}/register", json={
        "contact_name": "Test", "contact_email": "total@example.com",
        "payment_method": "ONLINE", "component_id": comp.id,
        "items": [{"product_id": product.id, "quantity": 3}],
    })
    assert resp.status_code == 200, resp.text

    from app.domains.payment_status.models import PaymentRecord
    from app.services.registration_totals import compute_registration_total
    from app.models.activity import Registration

    rec = db_session.query(PaymentRecord).filter(PaymentRecord.payable_type == "registration").first()
    reg = db_session.query(Registration).first()
    total, _lines = compute_registration_total(reg)
    assert total == Decimal("37.50")  # 3 × 12.50
    assert rec.amount == total
