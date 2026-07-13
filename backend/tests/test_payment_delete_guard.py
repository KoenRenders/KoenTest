"""Verwijderbescherming op betalingen (#218).

Een betaling waar effectief geld bewoog mag niet verdwijnen: een door Mollie
betaalde online betaling, of elk record met een ontvangen/betaald bedrag
(bevestigde cash/overschrijving of een uitgevoerde terugbetaling). Enkel
onbetaalde/pending records zonder bedrag blijven verwijderbaar (#167).
"""
from decimal import Decimal

from app.domains.payment.api import PaymentRecord


def _seed(db, *, method, status, amount="18.00", amount_paid="18.00", type="charge"):
    rec = PaymentRecord(
        payable_type="registration", payable_id=1,
        amount=Decimal(amount),
        amount_paid=Decimal(amount_paid) if amount_paid is not None else None,
        method=method, status=status, type=type,
    )
    db.add(rec)
    db.flush()
    return rec


def _delete(client, headers, rec_id):
    return client.delete(f"/api/v1/payment-status/records/{rec_id}", headers=headers)


def test_online_paid_cannot_be_deleted(client, db_session, admin_headers):
    rec = _seed(db_session, method="online", status="paid")
    resp = _delete(client, admin_headers, rec.id)
    assert resp.status_code == 400, resp.text
    assert "Mollie" in resp.json()["detail"]


def test_record_with_amount_paid_cannot_be_deleted(client, db_session, admin_headers):
    rec = _seed(db_session, method="transfer", status="paid", amount_paid="18.00")
    resp = _delete(client, admin_headers, rec.id)
    assert resp.status_code == 400, resp.text


def test_settled_refund_cannot_be_deleted(client, db_session, admin_headers):
    rec = _seed(db_session, method="transfer", status="paid",
                amount="-40.00", amount_paid="-40.00", type="refund")
    resp = _delete(client, admin_headers, rec.id)
    assert resp.status_code == 400, resp.text


def test_pending_unpaid_record_can_still_be_deleted(client, db_session, admin_headers):
    rec = _seed(db_session, method="transfer", status="pending", amount_paid=None)
    rid = rec.id
    resp = _delete(client, admin_headers, rid)
    assert resp.status_code == 204, resp.text
    assert db_session.query(PaymentRecord).filter(PaymentRecord.id == rid).first() is None


def test_can_delete_transfer_payment_after_correcting_amount_to_zero(client, db_session, admin_headers):
    """Correctieflow (#222): bewerken blijft toegestaan; zet het betaald bedrag op 0,
    dan mag de overschrijving wél verwijderd worden."""
    rec = _seed(db_session, method="transfer", status="paid", amount_paid="18.00")
    assert _delete(client, admin_headers, rec.id).status_code == 400  # eerst geweigerd
    patch = client.patch(f"/api/v1/payment-status/records/{rec.id}",
                         json={"status": "paid", "amount_paid": "0"}, headers=admin_headers)
    assert patch.status_code == 200, patch.text
    assert _delete(client, admin_headers, rec.id).status_code == 204


def test_can_delete_transfer_refund_after_correcting_amount_to_zero(client, db_session, admin_headers):
    """Idem voor een terugbetaling van type overschrijving (#222)."""
    rec = _seed(db_session, method="transfer", status="paid",
                amount="-40.00", amount_paid="-40.00", type="refund")
    assert _delete(client, admin_headers, rec.id).status_code == 400
    patch = client.patch(f"/api/v1/payment-status/records/{rec.id}",
                         json={"status": "paid", "amount_paid": "0"}, headers=admin_headers)
    assert patch.status_code == 200, patch.text
    assert _delete(client, admin_headers, rec.id).status_code == 204
