"""Gedeelde inschrijving-editor (#455/#451): de admin bewerkt aantallen,
regels toevoegen/verwijderen en de opmerking vanuit het detail-fragment. De
UI-routes hergebruiken de bestaande router-facades; sessie + CSRF vereist.
"""
from tests.conftest import SEEDED_ADMIN_EMAIL, seed_activity_with_product
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from app.domains.activities.api import Registration, RegistrationItem


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _register(client, activity_id, comp, product, quantity=1):
    resp = client.post(f"/api/v1/activities/{activity_id}/register", json={
        "contact_name": "An Janssens", "contact_email": "an@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": quantity}],
    })
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def _item_id(db, reg_id):
    return db.query(RegistrationItem).filter(
        RegistrationItem.registration_id == reg_id).first().id


def test_detail_requires_session(client, db_session):
    activity, comp, product = seed_activity_with_product(db_session, is_free=False)
    reg_id = _register(client, activity.id, comp, product)
    assert client.get(f"/admin/inschrijvingen/{reg_id}").status_code == 401


def test_editor_update_quantity_add_delete_and_remarks(client, db_session):
    activity, comp, product = seed_activity_with_product(db_session, is_free=False)
    reg_id = _register(client, activity.id, comp, product, quantity=1)
    item_id = _item_id(db_session, reg_id)
    csrf = _login(client)
    hdr = {"X-CSRF-Token": csrf}

    # Detail toont het product en een bewerkknop
    detail = client.get(f"/admin/inschrijvingen/{reg_id}")
    assert detail.status_code == 200 and product.name in detail.text

    # Aantal wijzigen → fragment toont het nieuwe aantal
    r = client.post(f"/admin/inschrijvingen/{reg_id}/regels/{item_id}",
                    data={"quantity": 4}, headers=hdr)
    assert r.status_code == 200 and "4×" in r.text
    db_session.expire_all()
    assert db_session.get(RegistrationItem, item_id).quantity == 4

    # Opmerking opslaan
    r = client.post(f"/admin/inschrijvingen/{reg_id}/opmerking",
                    data={"remarks": "Komt later"}, headers=hdr)
    assert r.status_code == 200 and "Komt later" in r.text
    db_session.expire_all()
    assert db_session.get(Registration, reg_id).remarks == "Komt later"

    # Regel verwijderen → geen producten meer
    r = client.post(f"/admin/inschrijvingen/{reg_id}/regels/{item_id}/verwijderen",
                    headers=hdr)
    assert r.status_code == 200

    # Regel opnieuw toevoegen
    r = client.post(f"/admin/inschrijvingen/{reg_id}/regels",
                    data={"product_id": product.id, "quantity": 2}, headers=hdr)
    assert r.status_code == 200 and "2×" in r.text


def test_editor_rejects_missing_csrf(client, db_session):
    activity, comp, product = seed_activity_with_product(db_session, is_free=False)
    reg_id = _register(client, activity.id, comp, product)
    item_id = _item_id(db_session, reg_id)
    _login(client)  # sessie zonder CSRF-header
    r = client.post(f"/admin/inschrijvingen/{reg_id}/regels/{item_id}",
                    data={"quantity": 9})
    assert r.status_code == 403
