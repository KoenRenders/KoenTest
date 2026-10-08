"""Gedeelde inschrijving-editor (#455/#451): de admin bewerkt aantallen,
regels toevoegen/verwijderen en de opmerking vanuit het detail-fragment. De
UI-routes hergebruiken de bestaande router-facades; sessie + CSRF vereist.
"""

from app.domains.activities.api import Registration, RegistrationItem
from app.domains.auth.api import SESSION_COOKIE, csrf_token_for, make_session_value
from tests.conftest import (
    SEEDED_ADMIN_EMAIL,
    register_at_the_door,
    seed_activity_with_product,
    sent_to_sign_in,
)


def _login(client):
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return csrf_token_for(value)


def _register(client, activity_id, comp, product, quantity=1):
    resp = register_at_the_door(
        client,
        activity_id,
        json={
            "contact_name": "An Janssens",
            "phone": "0470000000",
            "contact_email": "an@example.com",
            "component_id": comp.id,
            "payment_method": "transfer",
            "items": [{"product_id": product.id, "quantity": quantity}],
        },
    )
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def _item_id(db, reg_id):
    return db.query(RegistrationItem).filter(RegistrationItem.registration_id == reg_id).first().id


def test_detail_requires_session(client, db_session):
    activity, comp, product = seed_activity_with_product(db_session, is_free=False)
    reg_id = _register(client, activity.id, comp, product)
    assert sent_to_sign_in(client, f"/admin/inschrijvingen/{reg_id}")


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
    r = client.post(
        f"/admin/inschrijvingen/{reg_id}/regels/{item_id}", data={"quantity": 4}, headers=hdr
    )
    assert r.status_code == 200 and "4×" in r.text
    db_session.expire_all()
    assert db_session.get(RegistrationItem, item_id).quantity == 4

    # Opmerking opslaan
    r = client.post(
        f"/admin/inschrijvingen/{reg_id}/opmerking", data={"remarks": "Komt later"}, headers=hdr
    )
    assert r.status_code == 200 and "Komt later" in r.text
    db_session.expire_all()
    assert db_session.get(Registration, reg_id).remarks == "Komt later"

    # #1494: the counter to 0 and Save → no line any more (the separate
    # "Verwijderen" and "Toevoegen" routes are gone).
    r = client.post(
        f"/admin/inschrijvingen/{reg_id}/opslaan", data={f"product_{product.id}": "0"}, headers=hdr
    )
    assert r.status_code == 200
    db_session.expire_all()
    assert db_session.get(Registration, reg_id).items == []

    # The counter back to 2 and Save → one line again.
    r = client.post(
        f"/admin/inschrijvingen/{reg_id}/opslaan", data={f"product_{product.id}": "2"}, headers=hdr
    )
    assert r.status_code == 200 and "2×" in r.text


def test_editor_rejects_missing_csrf(client, db_session):
    activity, comp, product = seed_activity_with_product(db_session, is_free=False)
    reg_id = _register(client, activity.id, comp, product)
    item_id = _item_id(db_session, reg_id)
    _login(client)  # sessie zonder CSRF-header
    r = client.post(f"/admin/inschrijvingen/{reg_id}/regels/{item_id}", data={"quantity": 9})
    assert r.status_code == 403
