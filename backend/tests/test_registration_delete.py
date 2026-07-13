"""Admin verwijdert een hele inschrijving (soft-delete) (#313).

Financiële afhandeling is identiek aan het apart weghalen van álle producten
(reconcile, #185): een **onbetaalde** inschrijving verwijderen ruimt de openstaande
charge op (niets verschuldigd); een **betaalde** inschrijving verwijderen maakt een
terugbetaling-verplichting aan (geld = financieel feit, verdwijnt niet zomaar).
"""
from app.domains.activities.api import Registration
from app.domains.payment.api import PaymentRecord
from tests.conftest import seed_activity_with_product

_REG = {"contact_name": "An Janssens", "contact_email": "an@example.com", "payment_method": "TRANSFER"}


def _public(client, activity_id, comp_id):
    return client.get(
        f"/api/v1/activities/{activity_id}/public-registrations",
        params={"component_id": comp_id},
    ).json()


def _records(client, admin_headers):
    return client.get("/api/v1/payment-status/records", headers=admin_headers).json()


def _register(client, db_session, qty=2, price="18.00"):
    _, comp, product = seed_activity_with_product(db_session, price=price)
    client.post(f"/api/v1/activities/{comp.activity_id}/register", json={
        **_REG, "component_id": comp.id, "items": [{"product_id": product.id, "quantity": qty}]})
    reg = db_session.query(Registration).filter(Registration.activity_id == comp.activity_id).first()
    return comp, reg


def test_delete_registration_requires_admin(client, db_session):
    comp, reg = _register(client, db_session)
    resp = client.delete(f"/api/v1/activities/{comp.activity_id}/registrations/{reg.id}")
    assert resp.status_code in (401, 403)


def test_delete_unpaid_registration_clears_pending_charge(client, db_session, admin_headers):
    """Onbetaald verwijderen → weg uit de deelnemerslijst én de openstaande charge
    verdwijnt (niets verschuldigd voor een verwijderde inschrijving)."""
    comp, reg = _register(client, db_session)
    assert any(p["contact_name"] == "An Janssens" for p in _public(client, comp.activity_id, comp.id))

    resp = client.delete(
        f"/api/v1/activities/{comp.activity_id}/registrations/{reg.id}", headers=admin_headers)
    assert resp.status_code == 200, resp.text

    assert not any(p["contact_name"] == "An Janssens" for p in _public(client, comp.activity_id, comp.id))
    keys = [(r["payable_type"], r["payable_id"]) for r in _records(client, admin_headers)]
    assert ("registration", reg.id) not in keys  # pending charge opgeruimd


def test_delete_paid_registration_keeps_charge_and_creates_pending_refund(client, db_session, admin_headers):
    """Betaald verwijderen → identiek aan alle producten weghalen (#185): de betaalde
    charge blijft 'vereffend' (geld werd ontvangen) en er komt één **pending**
    terugbetaling bij (niet als teruggestort getoond tot de penningmeester bevestigt)."""
    comp, reg = _register(client, db_session)
    charge = db_session.query(PaymentRecord).filter(
        PaymentRecord.payable_type == "registration", PaymentRecord.type == "charge",
    ).order_by(PaymentRecord.created_at.desc()).first()
    client.patch(f"/api/v1/payment-status/records/{charge.id}",
                 json={"status": "paid", "amount_paid": "36.00"}, headers=admin_headers)

    resp = client.delete(
        f"/api/v1/activities/{comp.activity_id}/registrations/{reg.id}", headers=admin_headers)
    assert resp.status_code == 200, resp.text

    # Weg uit de publieke deelnemerslijst.
    assert not any(p["contact_name"] == "An Janssens" for p in _public(client, comp.activity_id, comp.id))

    recs = [r for r in _records(client, admin_headers)
            if r["payable_type"] == "registration" and r["payable_id"] == reg.id]
    charges = [r for r in recs if r["type"] == "charge"]
    refunds = [r for r in recs if r["type"] == "refund"]
    # De betaalde charge blijft bestaan en is 'vereffend' (amount_paid ingevuld).
    assert len(charges) == 1 and charges[0]["amount_paid"] is not None
    # Eén PENDING terugbetaling (amount_paid None → nog niet uitbetaald).
    assert len(refunds) == 1 and refunds[0]["amount_paid"] is None
