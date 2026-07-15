"""Admin-betaalacties (#455): vrije status-correctie, verwijderen (soft-delete
uit het saldo) en refund-correctie. Geldkritisch: elke actie moet het netto-
ontvangen bedrag correct beïnvloeden en een history-snapshot laten.
"""
from decimal import Decimal

import pytest

from app.domains.payment.api import (
    PaymentRecord, PaymentRecordHistory,
    create_refund, net_paid, set_payment_status, void_payment_record,
)


def _seed_charge(db, *, payable_id=1, amount="18.00", amount_paid="18.00", status="paid"):
    charge = PaymentRecord(
        payable_type="registration", payable_id=payable_id,
        amount=Decimal(amount),
        amount_paid=Decimal(amount_paid) if amount_paid is not None else None,
        method="transfer", status=status, type="charge",
    )
    db.add(charge)
    db.flush()
    return charge


def _history(db, record_id):
    return db.query(PaymentRecordHistory).filter(
        PaymentRecordHistory.payment_record_id == record_id).all()


def test_set_status_to_pending_clears_paid_and_stops_counting(db_session):
    charge = _seed_charge(db_session, amount="18.00", amount_paid="18.00", status="paid")
    assert net_paid(db_session, "registration", charge.payable_id) == Decimal("18.00")

    set_payment_status(db_session, charge.id, "pending", actor="admin@test")
    db_session.flush()
    assert charge.status == "pending"
    assert charge.amount_paid is None and charge.paid_at is None
    # Geld telt niet meer als ontvangen.
    assert net_paid(db_session, "registration", charge.payable_id) == Decimal("0.00")
    assert any(h.action == "payment_status_edited" for h in _history(db_session, charge.id))


def test_set_status_to_paid_sets_amount_paid(db_session):
    charge = _seed_charge(db_session, amount="20.00", amount_paid=None, status="pending")
    assert net_paid(db_session, "registration", charge.payable_id) == Decimal("0.00")

    set_payment_status(db_session, charge.id, "paid", actor="admin@test")
    db_session.flush()
    assert charge.status == "paid"
    assert charge.amount_paid == Decimal("20.00") and charge.paid_at is not None
    assert net_paid(db_session, "registration", charge.payable_id) == Decimal("20.00")


def test_set_status_rejects_unknown(db_session):
    charge = _seed_charge(db_session)
    with pytest.raises(ValueError, match="Ongeldige status"):
        set_payment_status(db_session, charge.id, "verzonnen", actor="admin@test")


def test_void_removes_charge_from_balance(db_session):
    charge = _seed_charge(db_session, amount="18.00", amount_paid="18.00")
    assert net_paid(db_session, "registration", charge.payable_id) == Decimal("18.00")

    void_payment_record(db_session, charge.id, actor="admin@test", note="dubbel geboekt")
    db_session.flush()
    # De globale soft-delete-filter sluit het record uit → telt niet meer mee.
    assert net_paid(db_session, "registration", charge.payable_id) == Decimal("0.00")
    assert any(h.action == "payment_voided" for h in _history(db_session, charge.id))


def test_void_refund_restores_available_balance(db_session):
    # Charge betaald, dan (fout) volledig terugbetaald → netto 0.
    charge = _seed_charge(db_session, amount="18.00", amount_paid="18.00")
    refund = create_refund(db_session, charge.id, Decimal("18.00"), actor="admin@test")
    assert net_paid(db_session, "registration", charge.payable_id) == Decimal("0.00")

    # Foute refund verwijderen → het ontvangen bedrag staat weer volledig.
    void_payment_record(db_session, refund.id, actor="admin@test")
    db_session.flush()
    assert net_paid(db_session, "registration", charge.payable_id) == Decimal("18.00")
