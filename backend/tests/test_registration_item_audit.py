"""Audit + bewerk-pad voor bestelregels (#84).

Wijzigingen aan een bestelling ná inschrijving/betaling (product wisselen, aantal
aanpassen, regel toevoegen/verwijderen) moeten auditeerbaar zijn én het
verschuldigde totaal herberekenen, zodat het saldo in het betaalscherm klopt en
een eventueel terug te betalen bedrag zichtbaar wordt.
"""
from decimal import Decimal

import pytest

from app.domains.activities.api import Registration, RegistrationItem
from app.domains.activities.api import ActivityProduct
from app.domains.activities.api import RegistrationItemHistory
from app.domains.payment.api import PaymentRecord
from tests.conftest import seed_activity_with_product


def _add_product(db, comp, *, name, price, is_free=False):
    p = ActivityProduct(component_id=comp.id, name=name, price=Decimal(str(price)), is_free=is_free)
    db.add(p)
    db.flush()
    return p


def _register(client, db, comp, product, qty=1):
    activity_id = comp.activity_id
    resp = client.post(f"/api/v1/activities/{activity_id}/register", json={
        "contact_name": "An Janssens", "contact_email": "an@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": qty}],
    })
    assert resp.status_code in (200, 201), resp.text
    reg = db.query(Registration).filter(
        Registration.component_id == comp.id
    ).order_by(Registration.id.desc()).first()
    item = db.query(RegistrationItem).filter(RegistrationItem.registration_id == reg.id).first()
    return activity_id, reg, item


def _history_for(db, item_id):
    return db.query(RegistrationItemHistory).filter(
        RegistrationItemHistory.registration_item_id == item_id
    ).order_by(RegistrationItemHistory.id).all()


def test_initial_registration_is_audited(client, db_session):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    _, _reg, item = _register(client, db_session, comp, product)
    rows = _history_for(db_session, item.id)
    assert len(rows) == 1
    assert rows[0].operation == "insert"
    assert rows[0].action == "order_created"
    assert rows[0].source == "registration"
    assert rows[0].quantity == 1
    assert rows[0].product_id == product.id


def test_update_quantity_recomputes_due_and_audits(client, db_session, admin_headers):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id, reg, item = _register(client, db_session, comp, product)

    resp = client.patch(
        f"/api/v1/activities/{activity_id}/registrations/{reg.id}/items/{item.id}",
        json={"quantity": 2}, headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert Decimal(str(resp.json()["balance"]["total_due"])) == Decimal("36.00")

    rows = _history_for(db_session, item.id)
    assert [r.action for r in rows] == ["order_created", "order_changed"]
    assert rows[-1].operation == "update"
    assert rows[-1].quantity == 2
    assert rows[-1].source == "admin_manual"


def test_swap_to_helper_product_auto_refunds(client, db_session, admin_headers):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    helper = _add_product(db_session, comp, name="Vlees - helper", price="0", is_free=True)
    activity_id, reg, item = _register(client, db_session, comp, product)

    # Penningmeester bevestigt de overschrijving van €18.
    charge = db_session.query(PaymentRecord).filter(
        PaymentRecord.payable_type == "registration", PaymentRecord.payable_id == reg.id,
    ).first()
    client.patch(f"/api/v1/payment-status/records/{charge.id}",
                 json={"status": "paid", "amount_paid": "18.00"}, headers=admin_headers)

    # Bestelregel naar de gratis helper-variant → verschuldigd 0; de €18 wordt als
    # terugbetaal-verplichting aangemaakt (#216), pending tot bevestiging.
    resp = client.patch(
        f"/api/v1/activities/{activity_id}/registrations/{reg.id}/items/{item.id}",
        json={"product_id": helper.id}, headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert Decimal(str(body["balance"]["total_due"])) == Decimal("0.00")
    assert Decimal(str(body["balance"]["balance"])) == Decimal("-18.00")
    assert body["refund_due"] is True
    assert Decimal(str(body["balance"]["total_refunded"])) == Decimal("0.00")

    # Penningmeester bevestigt de terugstorting → nu pas vereffend.
    refund = db_session.query(PaymentRecord).filter(
        PaymentRecord.payable_type == "registration", PaymentRecord.payable_id == reg.id,
        PaymentRecord.type == "refund").order_by(PaymentRecord.created_at.desc()).first()
    assert refund.status == "pending" and refund.amount_paid is None
    client.patch(f"/api/v1/payment-status/records/{refund.id}",
                 json={"status": "paid"}, headers=admin_headers)
    bal = client.get(f"/api/v1/payment-status/registrations/{reg.id}/balance",
                     headers=admin_headers).json()
    assert Decimal(str(bal["balance"])) == Decimal("0.00")
    assert Decimal(str(bal["total_refunded"])) == Decimal("18.00")


def test_add_order_line(client, db_session, admin_headers):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    extra = _add_product(db_session, comp, name="Dessert", price="5.00")
    activity_id, reg, _item = _register(client, db_session, comp, product)

    resp = client.post(
        f"/api/v1/activities/{activity_id}/registrations/{reg.id}/items",
        json={"product_id": extra.id, "quantity": 2}, headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    assert Decimal(str(resp.json()["balance"]["total_due"])) == Decimal("28.00")  # 18 + 2×5

    new_item = db_session.query(RegistrationItem).filter(
        RegistrationItem.registration_id == reg.id,
        RegistrationItem.product_id == extra.id,
    ).first()
    rows = _history_for(db_session, new_item.id)
    assert rows[0].operation == "insert"
    assert rows[0].action == "order_changed"


def test_delete_order_line_audited_before_delete(client, db_session, admin_headers):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id, reg, item = _register(client, db_session, comp, product)
    item_id = item.id

    resp = client.delete(
        f"/api/v1/activities/{activity_id}/registrations/{reg.id}/items/{item_id}",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    # Regel weg, maar de delete-snapshot bleef bestaan (overleeft de bron).
    assert db_session.query(RegistrationItem).filter(RegistrationItem.id == item_id).first() is None
    rows = _history_for(db_session, item_id)
    assert rows[-1].operation == "delete"
    assert rows[-1].action == "order_changed"
    assert rows[-1].quantity == 1  # toestand op moment van verwijderen


def test_product_from_other_activity_rejected(client, db_session, admin_headers):
    _, comp_a, product_a = seed_activity_with_product(db_session, price="18.00")
    _, _comp_b, product_b = seed_activity_with_product(db_session, price="9.00")
    activity_id, reg, item = _register(client, db_session, comp_a, product_a)

    resp = client.patch(
        f"/api/v1/activities/{activity_id}/registrations/{reg.id}/items/{item.id}",
        json={"product_id": product_b.id}, headers=admin_headers,
    )
    assert resp.status_code == 400


def test_registrations_expose_item_id(client, db_session, admin_headers):
    """De admin-registratielijst geeft het item-id mee, zodat de UI regels kan
    bewerken (#84)."""
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id, reg, item = _register(client, db_session, comp, product)
    resp = client.get(f"/api/v1/activities/{activity_id}/registrations", headers=admin_headers)
    assert resp.status_code == 200, resp.text
    items = resp.json()[0]["items"]
    assert items[0]["id"] == item.id


def test_order_line_edit_requires_admin(client, db_session):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id, reg, item = _register(client, db_session, comp, product)
    resp = client.patch(
        f"/api/v1/activities/{activity_id}/registrations/{reg.id}/items/{item.id}",
        json={"quantity": 2},
    )
    assert resp.status_code in (401, 403)
