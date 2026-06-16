"""Penningmeester-filter (#90): de records-lijst geeft genoeg context mee om per
lidmaatschap-vernieuwing of per activiteit-onderdeel te filteren."""
from tests.conftest import seed_activity_with_product


def test_registration_record_exposes_component(client, db_session, admin_headers):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id = comp.activity_id
    resp = client.post(f"/api/v1/activities/{activity_id}/register", json={
        "contact_name": "An", "contact_email": "an@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": 1}],
    })
    assert resp.status_code in (200, 201), resp.text

    records = client.get("/api/v1/payment-status/records", headers=admin_headers).json()
    reg_rec = next(r for r in records if r["payable_type"] == "registration")
    assert reg_rec["activity_id"] == activity_id
    assert reg_rec["component_id"] == comp.id
    assert reg_rec["component_name"] == comp.name
