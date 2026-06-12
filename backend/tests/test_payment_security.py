"""Veiligheids- en geldstroomtests: precies de grenzen waar een fout een lid
geld kost of data lekt."""
from decimal import Decimal

from tests.conftest import seed_postal_code, seed_activity_with_product


def _family_payload(email="lid@example.com", street="Milostraat", postal="2400"):
    return {
        "street": street,
        "house_number": "40",
        "postal_code": postal,
        "payment_method": "transfer",
        "members": [
            {
                "last_name": "Janssens", "first_name": "An",
                "email": email, "mobile": "0470123456",
                "relation_type": "HOOFDLID",
            }
        ],
    }


def test_membership_amount_is_server_side(client, db_session):
    """Het lidgeld wordt server-side bepaald; de client stuurt geen bedrag mee."""
    seed_postal_code(db_session)
    resp = client.post("/api/v1/families", json=_family_payload())
    assert resp.status_code == 201, resp.text
    # Volprijs uit config (35.00) of halfprijs (17.50) afhankelijk van de datum.
    assert Decimal(str(resp.json()["amount"])) in (Decimal("35.00"), Decimal("17.50"))


def test_activity_negative_quantity_rejected(client, db_session):
    _, comp, product = seed_activity_with_product(db_session)
    activity_id = comp.activity_id
    resp = client.post(f"/api/v1/activities/{activity_id}/register", json={
        "contact_name": "Test", "contact_email": "t@example.com",
        "component_id": comp.id,
        "items": [{"product_id": product.id, "quantity": -1}],
    })
    assert resp.status_code == 400


def test_activity_invalid_product_rejected(client, db_session):
    _, comp, product = seed_activity_with_product(db_session)
    activity_id = comp.activity_id
    resp = client.post(f"/api/v1/activities/{activity_id}/register", json={
        "contact_name": "Test", "contact_email": "t@example.com",
        "component_id": comp.id,
        "items": [{"product_id": product.id + 9999, "quantity": 1}],
    })
    assert resp.status_code == 400


def test_activity_quantity_over_max_rejected(client, db_session):
    from app.config import settings
    _, comp, product = seed_activity_with_product(db_session)
    activity_id = comp.activity_id
    resp = client.post(f"/api/v1/activities/{activity_id}/register", json={
        "contact_name": "Test", "contact_email": "t@example.com",
        "component_id": comp.id,
        "items": [{"product_id": product.id, "quantity": settings.max_item_quantity + 1}],
    })
    assert resp.status_code == 400


def test_membership_dedup_blocks_second(client, db_session):
    """Tweede registratie met hetzelfde e-mailadres + jaar wordt geblokkeerd."""
    seed_postal_code(db_session)
    first = client.post("/api/v1/families", json=_family_payload(email="dub@example.com"))
    assert first.status_code == 201, first.text
    second = client.post("/api/v1/families", json=_family_payload(email="dub@example.com"))
    assert second.status_code == 409


def test_membership_dedup_allows_after_failed_payment(client, db_session):
    """Een eerdere mislukte betaling blokkeert een nieuwe registratie niet."""
    seed_postal_code(db_session)
    first = client.post("/api/v1/families", json=_family_payload(email="retry@example.com"))
    assert first.status_code == 201

    # Zet het betaalrecord van die inschrijving op 'failed'.
    from app.domains.payment_status.models import PaymentRecord
    rec = db_session.query(PaymentRecord).filter(PaymentRecord.payable_type == "membership").first()
    rec.status = "failed"
    db_session.flush()

    second = client.post("/api/v1/families", json=_family_payload(email="retry@example.com"))
    assert second.status_code == 201, second.text


def test_activity_registration_limit_per_email(client, db_session):
    """Boven MAX_REGISTRATIONS_PER_EMAIL inschrijvingen → 409."""
    from app.config import settings
    _, comp, product = seed_activity_with_product(db_session, is_free=True)
    activity_id = comp.activity_id

    def register():
        return client.post(f"/api/v1/activities/{activity_id}/register", json={
            "contact_name": "Gezin", "contact_email": "gezin@example.com",
            "component_id": comp.id,
            "items": [{"product_id": product.id, "quantity": 1}],
        })

    for _ in range(settings.max_registrations_per_email):
        assert register().status_code == 200
    # De volgende overschrijdt de limiet.
    assert register().status_code == 409


def test_amount_paid_cannot_exceed_due(client, db_session, admin_headers):
    """Admin kan geen hoger betaald bedrag registreren dan verschuldigd."""
    seed_postal_code(db_session)
    client.post("/api/v1/families", json=_family_payload(email="pay@example.com"))
    from app.domains.payment_status.models import PaymentRecord
    rec = db_session.query(PaymentRecord).first()

    resp = client.patch(
        f"/api/v1/payment-status/records/{rec.id}",
        json={"amount_paid": float(rec.amount) + 100},
        headers=admin_headers,
    )
    assert resp.status_code == 400


def test_amount_paid_cannot_be_negative(client, db_session, admin_headers):
    """Admin kan geen negatief betaald bedrag registreren."""
    seed_postal_code(db_session)
    client.post("/api/v1/families", json=_family_payload(email="neg@example.com"))
    from app.domains.payment_status.models import PaymentRecord
    rec = db_session.query(PaymentRecord).first()

    resp = client.patch(
        f"/api/v1/payment-status/records/{rec.id}",
        json={"amount_paid": -5},
        headers=admin_headers,
    )
    assert resp.status_code == 400


def test_activity_invalid_email_rejected(client, db_session):
    """Een ongeldig e-mailadres bij inschrijving wordt server-side geweigerd (422)."""
    _, comp, product = seed_activity_with_product(db_session)
    activity_id = comp.activity_id
    resp = client.post(f"/api/v1/activities/{activity_id}/register", json={
        "contact_name": "X", "contact_email": "geen-email",
        "component_id": comp.id,
        "items": [{"product_id": product.id, "quantity": 1}],
    })
    assert resp.status_code == 422


def test_negative_product_price_rejected(client, db_session, admin_headers):
    """Admin kan geen product met een negatieve prijs aanmaken."""
    activity, comp, _product = seed_activity_with_product(db_session)
    resp = client.post(
        f"/api/v1/activities/{activity.id}/components/{comp.id}/products",
        json={"name": "Negatief", "price": -1, "is_free": False},
        headers=admin_headers,
    )
    # 422 = vorm-validatie; 400 = expliciete afwijzing; 500 = DB-constraint vangnet.
    assert resp.status_code in (422, 400, 500)


def test_login_rate_limited(client):
    """De login-limiter geeft 429 na te veel pogingen per minuut."""
    saw_429 = False
    for _ in range(11):
        r = client.post("/api/v1/auth/request-login",
                        json={"email": "ratelimit-test@example.com"})
        if r.status_code == 429:
            saw_429 = True
            break
    assert saw_429


def test_refresh_endpoint_requires_auth(client):
    """Het refresh-endpoint van een betaalrecord eist admin-auth."""
    resp = client.post(
        "/api/v1/payment-status/records/00000000-0000-0000-0000-000000000000/refresh"
    )
    assert resp.status_code in (401, 403)


def test_admin_endpoints_require_auth(client):
    """Zonder geldig admin-token geen toegang tot de betaaladministratie."""
    resp = client.get("/api/v1/payment-status/records")
    assert resp.status_code == 401


def test_public_payment_endpoint_hides_checkout_url(client, db_session):
    """Het publieke gateway-endpoint mag de betaallink niet teruggeven."""
    from decimal import Decimal
    from app.domains.payment_gateway.models import GatewayPayment
    gp = GatewayPayment(
        provider="mollie", provider_payment_id="tr_x", amount=Decimal("10.00"),
        status="pending", checkout_url="https://mollie.test/checkout/tr_x",
        payment_metadata={},
    )
    db_session.add(gp)
    db_session.flush()

    resp = client.get(f"/api/v1/payment-gateway/payments/{gp.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert "checkout_url" not in body
    assert body["status"] == "pending"
