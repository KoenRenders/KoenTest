"""Financieel grootboek: terugbetalingen als apart negatief PaymentRecord (#83).

De invarianten die geld kosten als ze fout gaan: een refund draait enkel een
charge terug, je betaalt nooit meer terug dan ontvangen, en de stand per
inschrijving (verschuldigd vs. netto betaald) klopt met de live DB.
"""
from decimal import Decimal

import pytest

from app.domains.payment.api import PaymentRecord
from app.domains.payment.api import (
    create_refund, net_paid, registration_balance,
)
from app.domains.payment.api import PaymentRecordHistory
from tests.conftest import seed_activity_with_product


def _seed_charge(db, *, payable_id=1, amount="18.00", amount_paid="18.00", status="paid"):
    charge = PaymentRecord(
        payable_type="registration",
        payable_id=payable_id,
        amount=Decimal(amount),
        amount_paid=Decimal(amount_paid) if amount_paid is not None else None,
        method="transfer",
        status=status,
        type="charge",
    )
    db.add(charge)
    db.flush()
    return charge


def test_refund_creates_negative_record_linked_to_charge(db_session):
    charge = _seed_charge(db_session)
    refund = create_refund(db_session, charge.id, Decimal("18.00"), actor="admin@test")

    assert refund.type == "refund"
    assert refund.amount == Decimal("-18.00")
    assert refund.amount_paid == Decimal("-18.00")
    assert refund.refund_of_id == charge.id
    assert refund.status == "paid"
    # Na een volledige terugbetaling is er netto niets meer ontvangen.
    assert net_paid(db_session, "registration", charge.payable_id) == Decimal("0.00")


def test_partial_refund_leaves_remaining_balance(db_session):
    charge = _seed_charge(db_session, amount="18.00", amount_paid="18.00")
    create_refund(db_session, charge.id, Decimal("5.00"), actor="admin@test")
    assert net_paid(db_session, "registration", charge.payable_id) == Decimal("13.00")


def test_cannot_refund_more_than_received(db_session):
    charge = _seed_charge(db_session, amount="18.00", amount_paid="18.00")
    with pytest.raises(ValueError, match="netto ontvangen"):
        create_refund(db_session, charge.id, Decimal("20.00"))


def test_cannot_refund_more_than_received_across_two_refunds(db_session):
    charge = _seed_charge(db_session, amount="18.00", amount_paid="18.00")
    create_refund(db_session, charge.id, Decimal("12.00"))
    # Nog 6 over; 7 terugbetalen moet falen.
    with pytest.raises(ValueError, match="netto ontvangen"):
        create_refund(db_session, charge.id, Decimal("7.00"))


def test_cannot_refund_a_refund(db_session):
    charge = _seed_charge(db_session)
    refund = create_refund(db_session, charge.id, Decimal("5.00"))
    with pytest.raises(ValueError, match="charge"):
        create_refund(db_session, refund.id, Decimal("1.00"))


def test_refund_amount_must_be_positive(db_session):
    charge = _seed_charge(db_session)
    with pytest.raises(ValueError, match="positief"):
        create_refund(db_session, charge.id, Decimal("0"))


def test_refund_writes_audit_history(db_session):
    charge = _seed_charge(db_session)
    refund = create_refund(db_session, charge.id, Decimal("5.00"), actor="admin@test")
    rows = db_session.query(PaymentRecordHistory).filter(
        PaymentRecordHistory.payment_record_id == refund.id,
    ).all()
    assert len(rows) == 1
    assert rows[0].action == "payment_refunded"
    assert rows[0].type == "refund"
    assert rows[0].amount == Decimal("-5.00")


# ── Pending refund bevestigen (#219) ──────────────────────────────────────────

def test_confirm_pending_refund_books_full_amount(client, db_session, admin_headers):
    """Een pending refund bevestigen (status=paid, géén bedrag) boekt het volledige
    negatieve bedrag; de tekengevoelige validatie blokkeert dit niet (#219)."""
    charge = _seed_charge(db_session)
    refund = create_refund(db_session, charge.id, Decimal("18.00"), settled=False)
    assert refund.status == "pending" and refund.amount_paid is None
    resp = client.patch(f"/api/v1/payment-status/records/{refund.id}",
                        json={"status": "paid"}, headers=admin_headers)
    assert resp.status_code == 200, resp.text
    assert Decimal(str(resp.json()["amount_paid"])) == Decimal("-18.00")


def test_refund_rejects_positive_amount_paid(client, db_session, admin_headers):
    """Een positief betaald bedrag op een (negatieve) refund wordt geweigerd."""
    charge = _seed_charge(db_session)
    refund = create_refund(db_session, charge.id, Decimal("18.00"), settled=False)
    resp = client.patch(f"/api/v1/payment-status/records/{refund.id}",
                        json={"status": "paid", "amount_paid": "5.00"}, headers=admin_headers)
    assert resp.status_code == 400, resp.text


# ── Endpoint-laag (admin-only) ────────────────────────────────────────────────

def test_refund_endpoint_requires_admin(client):
    resp = client.post("/api/v1/payment-status/records/whatever/refund", json={"amount": "5.00"})
    assert resp.status_code in (401, 403)


def test_refund_endpoint_creates_refund(client, db_session, admin_headers):
    charge = _seed_charge(db_session)
    resp = client.post(
        f"/api/v1/payment-status/records/{charge.id}/refund",
        json={"amount": "18.00", "note": "lid afgehaakt"},
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["type"] == "refund"
    assert Decimal(str(body["amount"])) == Decimal("-18.00")
    assert body["refund_of_id"] == charge.id


def test_refund_endpoint_rejects_over_refund(client, db_session, admin_headers):
    charge = _seed_charge(db_session, amount="18.00", amount_paid="18.00")
    resp = client.post(
        f"/api/v1/payment-status/records/{charge.id}/refund",
        json={"amount": "25.00"},
        headers=admin_headers,
    )
    assert resp.status_code == 400


# ── Saldo per inschrijving (live DB als waarheid) ─────────────────────────────

def test_registration_balance_reflects_charge_and_refund(client, db_session, admin_headers):
    _, comp, product = seed_activity_with_product(db_session, price="18.00")
    activity_id = comp.activity_id

    reg_resp = client.post(f"/api/v1/activities/{activity_id}/register", json={
        "contact_name": "An Janssens", "contact_email": "an@example.com",
        "component_id": comp.id, "payment_method": "TRANSFER",
        "items": [{"product_id": product.id, "quantity": 1}],
    })
    assert reg_resp.status_code in (200, 201), reg_resp.text

    charge = db_session.query(PaymentRecord).filter(
        PaymentRecord.payable_type == "registration",
        PaymentRecord.type == "charge",
    ).order_by(PaymentRecord.created_at.desc()).first()
    assert charge is not None
    registration_id = charge.payable_id

    # Penningmeester bevestigt de overschrijving, daarna deels terugbetalen.
    client.patch(
        f"/api/v1/payment-status/records/{charge.id}",
        json={"status": "paid", "amount_paid": "18.00"}, headers=admin_headers,
    )
    client.post(
        f"/api/v1/payment-status/records/{charge.id}/refund",
        json={"amount": "5.00"}, headers=admin_headers,
    )

    resp = client.get(
        f"/api/v1/payment-status/registrations/{registration_id}/balance",
        headers=admin_headers,
    )
    assert resp.status_code == 200, resp.text
    bal = resp.json()
    assert Decimal(str(bal["total_due"])) == Decimal("18.00")
    assert Decimal(str(bal["total_paid"])) == Decimal("13.00")
    assert Decimal(str(bal["total_refunded"])) == Decimal("5.00")
    assert Decimal(str(bal["balance"])) == Decimal("5.00")
