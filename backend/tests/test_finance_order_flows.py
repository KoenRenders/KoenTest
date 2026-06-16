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


def test_order_lowered_after_payment_auto_refunds(client, db_session, admin_headers):
    """#191: een betaalde bestelling verlagen maakt automatisch een terugbetaling aan;
    het saldo vereffent meteen (geen handmatige refund-stap meer)."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id, reg, charge = _register(client, db_session, comp, product, qty=2)  # verschuldigd 36
    _pay(client, admin_headers, charge.id, "36.00")

    item = db_session.query(RegistrationItem).filter(RegistrationItem.registration_id == reg.id).first()
    resp = client.patch(
        f"/api/v1/activities/{activity_id}/registrations/{reg.id}/items/{item.id}",
        json={"quantity": 1}, headers=admin_headers,   # verschuldigd zakt naar 18
    )
    body = resp.json()
    assert Decimal(str(body["balance"]["balance"])) == Decimal("0.00")        # auto-refund vereffent
    assert body["refund_due"] is False
    assert Decimal(str(body["balance"]["total_refunded"])) == Decimal("18.00")

    db_session.expire_all()
    refund = db_session.query(PaymentRecord).filter(
        PaymentRecord.payable_type == "registration", PaymentRecord.payable_id == reg.id,
        PaymentRecord.type == "refund",
    ).one()
    assert Decimal(str(refund.amount)) == Decimal("-18.00")
    assert refund.refund_of_id == charge.id


def test_order_decrease_does_not_double_refund(client, db_session, admin_headers):
    """#191: een tweede (no-op) edit maakt geen tweede terugbetaling."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id, reg, charge = _register(client, db_session, comp, product, qty=2)  # 36
    _pay(client, admin_headers, charge.id, "36.00")
    item = db_session.query(RegistrationItem).filter(RegistrationItem.registration_id == reg.id).first()
    for _ in range(2):
        client.patch(f"/api/v1/activities/{activity_id}/registrations/{reg.id}/items/{item.id}",
                     json={"quantity": 1}, headers=admin_headers)
    db_session.expire_all()
    refunds = db_session.query(PaymentRecord).filter(
        PaymentRecord.payable_type == "registration", PaymentRecord.payable_id == reg.id,
        PaymentRecord.type == "refund",
    ).all()
    assert len(refunds) == 1


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


def _charges(db, reg):
    db.expire_all()
    return db.query(PaymentRecord).filter(
        PaymentRecord.payable_type == "registration", PaymentRecord.payable_id == reg.id,
        PaymentRecord.type == "charge",
    ).all()


def test_order_increase_creates_supplemental_transfer_charge(client, db_session, admin_headers):
    """#185 (C): een bestelregel toevoegen maakt een aanvullende charge voor het
    verschil aan — transfer + pending, met OGM — zodat het saldo in het
    betalingenoverzicht klopt met een eerlijke methode."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    extra = _add_product(db_session, comp, name="Dessert", price="16.00")
    activity_id, reg, charge = _register(client, db_session, comp, product, qty=1)  # €18
    _pay(client, admin_headers, charge.id, "18.00")

    client.post(
        f"/api/v1/activities/{activity_id}/registrations/{reg.id}/items",
        json={"product_id": extra.id, "quantity": 1}, headers=admin_headers,  # +€16
    )
    amounts = sorted(Decimal(str(c.amount)) for c in _charges(db_session, reg))
    assert amounts == [Decimal("16.00"), Decimal("18.00")]
    supp = next(c for c in _charges(db_session, reg) if Decimal(str(c.amount)) == Decimal("16.00"))
    assert supp.method == "transfer"
    assert supp.status == "pending"
    assert supp.structured_communication  # OGM aanwezig


def test_paying_supplemental_charge_settles_balance(client, db_session, admin_headers):
    """#185 (C): de aanvullende charge op 'betaald' zetten vereffent het saldo."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    extra = _add_product(db_session, comp, name="Dessert", price="16.00")
    activity_id, reg, charge = _register(client, db_session, comp, product, qty=1)
    _pay(client, admin_headers, charge.id, "18.00")
    client.post(f"/api/v1/activities/{activity_id}/registrations/{reg.id}/items",
                json={"product_id": extra.id, "quantity": 1}, headers=admin_headers)
    supp = next(c for c in _charges(db_session, reg) if Decimal(str(c.amount)) == Decimal("16.00"))
    _pay(client, admin_headers, supp.id, "16.00")
    bal = client.get(f"/api/v1/payment-status/registrations/{reg.id}/balance", headers=admin_headers).json()
    assert Decimal(str(bal["balance"])) == Decimal("0.00")


def test_lowering_unpaid_order_shrinks_supplemental_charge(client, db_session, admin_headers):
    """#185 (C): een nog niet-betaalde aanvullende bestelling weer verlagen laat de
    aanvullende pending-charge mee krimpen (geen overstaande charge)."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    extra = _add_product(db_session, comp, name="Dessert", price="16.00")
    activity_id, reg, charge = _register(client, db_session, comp, product, qty=1)  # €18 pending, onbetaald
    client.post(f"/api/v1/activities/{activity_id}/registrations/{reg.id}/items",
                json={"product_id": extra.id, "quantity": 2}, headers=admin_headers)  # +€32 → aanvullende charge €32
    assert sorted(Decimal(str(c.amount)) for c in _charges(db_session, reg)) == [Decimal("18.00"), Decimal("32.00")]

    item = db_session.query(RegistrationItem).filter(
        RegistrationItem.registration_id == reg.id, RegistrationItem.product_id == extra.id,
    ).first()
    client.patch(f"/api/v1/activities/{activity_id}/registrations/{reg.id}/items/{item.id}",
                 json={"quantity": 1}, headers=admin_headers)  # extra → €16, aanvullende charge moet €16 worden
    amounts = sorted(Decimal(str(c.amount)) for c in _charges(db_session, reg))
    assert amounts == [Decimal("16.00"), Decimal("18.00")]


def test_quantity_increase_creates_supplemental_charge(client, db_session, admin_headers):
    """#185 (C): óók een aantalverhoging (geen los product) maakt een aanvullende charge."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id, reg, charge = _register(client, db_session, comp, product, qty=1)  # €18
    _pay(client, admin_headers, charge.id, "18.00")
    item = db_session.query(RegistrationItem).filter(RegistrationItem.registration_id == reg.id).first()
    client.patch(f"/api/v1/activities/{activity_id}/registrations/{reg.id}/items/{item.id}",
                 json={"quantity": 3}, headers=admin_headers)  # €54 → +€36
    amounts = sorted(Decimal(str(c.amount)) for c in _charges(db_session, reg))
    assert amounts == [Decimal("18.00"), Decimal("36.00")]


def test_deleted_order_line_excluded_from_balance(client, db_session, admin_headers):
    """#194: een soft-deleted bestelregel telt niet meer mee in het verschuldigde
    (lazy relationship-load wordt nu ook gefilterd)."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    extra = _add_product(db_session, comp, name="Dessert", price="5.00")
    activity_id, reg, charge = _register(client, db_session, comp, product, qty=1)  # 18
    client.post(f"/api/v1/activities/{activity_id}/registrations/{reg.id}/items",
                json={"product_id": extra.id, "quantity": 1}, headers=admin_headers)  # +5 → 23
    bal = client.get(f"/api/v1/payment-status/registrations/{reg.id}/balance", headers=admin_headers).json()
    assert Decimal(str(bal["total_due"])) == Decimal("23.00")

    item = db_session.query(RegistrationItem).filter(
        RegistrationItem.registration_id == reg.id, RegistrationItem.product_id == extra.id).first()
    client.delete(f"/api/v1/activities/{activity_id}/registrations/{reg.id}/items/{item.id}", headers=admin_headers)
    bal = client.get(f"/api/v1/payment-status/registrations/{reg.id}/balance", headers=admin_headers).json()
    assert Decimal(str(bal["total_due"])) == Decimal("18.00")  # verwijderde regel telt niet meer


def test_partial_payment_lower_via_patch_reduces_to_paid(client, db_session, admin_headers):
    """#193: een partieel betaalde charge krimpt bij verlaging tot het betaalde deel,
    zonder terugbetaling (enkel het onbetaalde deel vervalt)."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id, reg, charge = _register(client, db_session, comp, product, qty=2)  # 36, pending
    _pay(client, admin_headers, charge.id, "18.00")  # partieel 18 van 36

    item = db_session.query(RegistrationItem).filter(RegistrationItem.registration_id == reg.id).first()
    client.patch(f"/api/v1/activities/{activity_id}/registrations/{reg.id}/items/{item.id}",
                 json={"quantity": 1}, headers=admin_headers)  # D = 18
    charges = _charges(db_session, reg)
    assert len(charges) == 1
    assert Decimal(str(charges[0].amount)) == Decimal("18.00")  # gekrompen tot het betaalde deel
    refunds = db_session.query(PaymentRecord).filter(
        PaymentRecord.payable_type == "registration", PaymentRecord.payable_id == reg.id,
        PaymentRecord.type == "refund").all()
    assert refunds == []


def test_partial_payment_remove_extra_refunds_only_received(client, db_session, admin_headers):
    """#193: na een partiële betaling op een aanvullende charge wordt bij het verwijderen
    enkel het te véél ontvangene terugbetaald (niet het volledige charge-bedrag); geen 500."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    extra = _add_product(db_session, comp, name="Dessert", price="18.00")
    activity_id, reg, charge = _register(client, db_session, comp, product, qty=1)  # 18
    _pay(client, admin_headers, charge.id, "18.00")  # origineel volledig betaald
    client.post(f"/api/v1/activities/{activity_id}/registrations/{reg.id}/items",
                json={"product_id": extra.id, "quantity": 1}, headers=admin_headers)  # +18 → supplement
    supp = next(c for c in _charges(db_session, reg) if c.id != charge.id)
    _pay(client, admin_headers, supp.id, "8.00")  # partieel 8 → netto ontvangen 26

    item = db_session.query(RegistrationItem).filter(
        RegistrationItem.registration_id == reg.id, RegistrationItem.product_id == extra.id).first()
    resp = client.delete(f"/api/v1/activities/{activity_id}/registrations/{reg.id}/items/{item.id}",
                         headers=admin_headers)  # D = 18
    assert resp.status_code == 200, resp.text  # geen 500
    db_session.expire_all()
    refunds = db_session.query(PaymentRecord).filter(
        PaymentRecord.payable_type == "registration", PaymentRecord.payable_id == reg.id,
        PaymentRecord.type == "refund").all()
    assert sum((Decimal(str(r.amount)) for r in refunds), Decimal("0")) == Decimal("-8.00")
    bal = client.get(f"/api/v1/payment-status/registrations/{reg.id}/balance", headers=admin_headers).json()
    assert Decimal(str(bal["balance"])) == Decimal("0.00")


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
