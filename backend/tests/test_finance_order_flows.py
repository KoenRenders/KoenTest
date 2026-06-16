"""End-to-end interacties tussen bestelwijzigingen en betalingen/refunds (#83+#84).

De invarianten die geld kosten als ze fout lopen: een bestelling verlagen ná
betaling → terugbetaling → saldo settelt; verhogen → saldo blijft openstaan;
en een refund op een lidmaatschap-betaling (niet enkel registratie)."""
from decimal import Decimal

from app.domains.payment_status.models import PaymentRecord
from app.models.activity import Registration, RegistrationItem
from app.models.activity_sub_registration import ActivityProduct
from app.models.member import Member, Membership
from tests.conftest import seed_activity_with_product, seed_postal_code


def _add_product(db, comp, *, name, price):
    p = ActivityProduct(component_id=comp.id, name=name, price=Decimal(str(price)), is_free=False)
    db.add(p)
    db.flush()
    return p


def _register(client, db, comp, product, qty=1):
    activity_id = comp.activity_id
    resp = client.post(f"/api/v1/activities/{activity_id}/register", json={
        "contact_name": "An", "contact_email": "an@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": qty}],
    })
    assert resp.status_code in (200, 201), resp.text
    reg = db.query(Registration).filter(Registration.component_id == comp.id).order_by(Registration.id.desc()).first()
    charge = db.query(PaymentRecord).filter(
        PaymentRecord.payable_type == "registration", PaymentRecord.payable_id == reg.id,
        PaymentRecord.type == "charge",
    ).first()
    return activity_id, reg, charge


def _pay(client, admin_headers, charge_id, amount):
    r = client.patch(f"/api/v1/payment-status/records/{charge_id}",
                     json={"status": "paid", "amount_paid": str(amount)}, headers=admin_headers)
    assert r.status_code == 200, r.text


def test_order_lowered_after_payment_then_refund_settles(client, db_session, admin_headers):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id, reg, charge = _register(client, db_session, comp, product, qty=2)  # verschuldigd 36
    _pay(client, admin_headers, charge.id, "36.00")

    item = db_session.query(RegistrationItem).filter(RegistrationItem.registration_id == reg.id).first()
    resp = client.patch(
        f"/api/v1/activities/{activity_id}/registrations/{reg.id}/items/{item.id}",
        json={"quantity": 1}, headers=admin_headers,   # verschuldigd zakt naar 18
    )
    body = resp.json()
    assert Decimal(str(body["balance"]["balance"])) == Decimal("-18.00")  # €18 te veel betaald
    assert body["refund_due"] is True

    client.post(f"/api/v1/payment-status/records/{charge.id}/refund",
                json={"amount": "18.00"}, headers=admin_headers)
    bal = client.get(f"/api/v1/payment-status/registrations/{reg.id}/balance", headers=admin_headers).json()
    assert Decimal(str(bal["balance"])) == Decimal("0.00")
    assert Decimal(str(bal["total_refunded"])) == Decimal("18.00")


def test_order_increased_after_payment_leaves_balance_owed(client, db_session, admin_headers):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    extra = _add_product(db_session, comp, name="Dessert", price="18.00")
    activity_id, reg, charge = _register(client, db_session, comp, product, qty=1)  # verschuldigd 18
    _pay(client, admin_headers, charge.id, "18.00")

    resp = client.post(
        f"/api/v1/activities/{activity_id}/registrations/{reg.id}/items",
        json={"product_id": extra.id, "quantity": 1}, headers=admin_headers,  # verschuldigd 36
    )
    body = resp.json()
    assert Decimal(str(body["balance"]["total_due"])) == Decimal("36.00")
    assert Decimal(str(body["balance"]["balance"])) == Decimal("18.00")  # nog €18 te ontvangen
    assert body["refund_due"] is False


def test_refund_on_membership_payment(client, db_session, admin_headers):
    seed_postal_code(db_session)
    resp = client.post("/api/v1/families", json={
        "street": "Milostraat", "house_number": "40", "postal_code": "2400",
        "payment_method": "transfer",
        "members": [{"last_name": "Janssens", "first_name": "An", "email": "an@example.com",
                     "mobile": "0470123456", "relation_type": "HOOFDLID"}],
    })
    assert resp.status_code == 201, resp.text
    member = db_session.query(Member).order_by(Member.id.desc()).first()
    ms = db_session.query(Membership).filter(Membership.member_id == member.id).first()
    charge = db_session.query(PaymentRecord).filter(
        PaymentRecord.payable_type == "membership", PaymentRecord.payable_id == ms.id,
    ).first()
    _pay(client, admin_headers, charge.id, str(charge.amount))

    r = client.post(f"/api/v1/payment-status/records/{charge.id}/refund",
                    json={"amount": "5.00", "note": "korting"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    refund = r.json()
    assert refund["type"] == "refund"
    assert Decimal(str(refund["amount"])) == Decimal("-5.00")
    assert refund["refund_of_id"] == charge.id
