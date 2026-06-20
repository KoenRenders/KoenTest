"""Admin verwijdert een hele inschrijving (soft-delete) — de betaling blijft
bewaard (#313). Geld is een financieel feit: het soft-deleten van een inschrijving
mag de ``PaymentRecord`` niet doen verdwijnen uit het betaaloverzicht.
"""
from app.models.activity import Registration
from tests.conftest import seed_activity_with_product

_REG = {"contact_name": "An Janssens", "contact_email": "an@example.com", "payment_method": "TRANSFER"}


def _public(client, activity_id, comp_id):
    return client.get(
        f"/api/v1/activities/{activity_id}/public-registrations",
        params={"component_id": comp_id},
    ).json()


def _payment_keys(client, admin_headers):
    recs = client.get("/api/v1/payment-status/records", headers=admin_headers).json()
    return [(r["payable_type"], r["payable_id"]) for r in recs]


def test_delete_registration_requires_admin(client, db_session):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    client.post(f"/api/v1/activities/{comp.activity_id}/register", json={
        **_REG, "component_id": comp.id, "items": [{"product_id": product.id, "quantity": 1}]})
    reg = db_session.query(Registration).filter(Registration.activity_id == comp.activity_id).first()
    resp = client.delete(f"/api/v1/activities/{comp.activity_id}/registrations/{reg.id}")
    assert resp.status_code in (401, 403)


def test_delete_registration_preserves_payment(client, db_session, admin_headers):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    client.post(f"/api/v1/activities/{comp.activity_id}/register", json={
        **_REG, "component_id": comp.id, "items": [{"product_id": product.id, "quantity": 2}]})
    reg = db_session.query(Registration).filter(Registration.activity_id == comp.activity_id).first()

    # Vóór: zichtbaar in de publieke deelnemerslijst + betaling bestaat.
    assert any(p["contact_name"] == "An Janssens" for p in _public(client, comp.activity_id, comp.id))
    assert ("registration", reg.id) in _payment_keys(client, admin_headers)

    # Verwijderen (admin).
    resp = client.delete(
        f"/api/v1/activities/{comp.activity_id}/registrations/{reg.id}", headers=admin_headers)
    assert resp.status_code == 200, resp.text

    # Ná: weg uit de publieke lijst …
    assert not any(p["contact_name"] == "An Janssens" for p in _public(client, comp.activity_id, comp.id))
    # … maar de betaling blijft bestaan én zichtbaar in het overzicht (geld = financieel feit).
    assert ("registration", reg.id) in _payment_keys(client, admin_headers)
