"""Admin bewerkt de opmerking van de inschrijver (#283): autorisatie, zetten/
wijzigen/wissen (→ NULL), soft-deleted niet bewerkbaar, en bestelregels/saldo
blijven ongemoeid."""
from app.models.activity import Registration
from app.soft_delete import soft_delete
from tests.conftest import seed_activity_with_product


def _register(client, activity_id, comp, product, remarks=None):
    payload = {
        "contact_name": "An Janssens", "contact_email": "an@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": 2}],
    }
    if remarks is not None:
        payload["remarks"] = remarks
    resp = client.post(f"/api/v1/activities/{activity_id}/register", json=payload)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def test_remarks_update_requires_admin(client, db_session):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    reg_id = _register(client, comp.activity_id, comp, product)
    resp = client.patch(
        f"/api/v1/activities/{comp.activity_id}/registrations/{reg_id}",
        json={"remarks": "geen toegang"},
    )
    assert resp.status_code in (401, 403)


def test_admin_can_set_change_and_clear_remarks(client, db_session, admin_headers):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id = comp.activity_id
    reg_id = _register(client, activity_id, comp, product)

    # Zetten
    r = client.patch(f"/api/v1/activities/{activity_id}/registrations/{reg_id}",
                     json={"remarks": "Komt iets later"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["remarks"] == "Komt iets later"

    # Wijzigen
    r = client.patch(f"/api/v1/activities/{activity_id}/registrations/{reg_id}",
                     json={"remarks": "Toch op tijd"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["remarks"] == "Toch op tijd"

    # Wissen: enkel witruimte wordt genormaliseerd naar NULL
    r = client.patch(f"/api/v1/activities/{activity_id}/registrations/{reg_id}",
                     json={"remarks": "   "}, headers=admin_headers)
    assert r.status_code == 200, r.text
    assert r.json()["remarks"] is None
    db_session.expire_all()
    assert db_session.get(Registration, reg_id).remarks is None


def test_remarks_update_leaves_order_lines_untouched(client, db_session, admin_headers):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id = comp.activity_id
    reg_id = _register(client, activity_id, comp, product)

    r = client.patch(f"/api/v1/activities/{activity_id}/registrations/{reg_id}",
                     json={"remarks": "notitie"}, headers=admin_headers)
    assert r.status_code == 200, r.text
    body = r.json()
    # Bestelregel blijft ongemoeid: nog steeds één regel met aantal 2.
    assert len(body["items"]) == 1
    assert body["items"][0]["quantity"] == 2


def test_remarks_update_on_soft_deleted_returns_404(client, db_session, admin_headers):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id = comp.activity_id
    reg_id = _register(client, activity_id, comp, product)

    reg = db_session.get(Registration, reg_id)
    soft_delete(reg)
    db_session.commit()

    r = client.patch(f"/api/v1/activities/{activity_id}/registrations/{reg_id}",
                     json={"remarks": "mag niet"}, headers=admin_headers)
    assert r.status_code == 404
