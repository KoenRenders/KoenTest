"""Geünificeerde 'Bewerken'-editor voor betalingen (#515): status + betaald bedrag
+ opmerking in één bewerking, voor charges én refunds. De invarianten die geld
kosten als ze fout gaan (tekengevoelige grenzen, effectieve uitbetaling van een
refund registreren, opmerking bewaard in de audit) worden hier bewaakt.
"""
from decimal import Decimal

import pytest

from app.domains.payment.api import (
    PaymentRecord, PaymentRecordHistory, create_refund, edit_payment_record, net_paid,
)


def _seed_charge(db, *, payable_id=1, amount="10.00", amount_paid=None, status="pending"):
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


def test_charge_status_paid_leeg_bedrag_boekt_volledig(db_session):
    """v1.4-gedrag: status→Betaald met leeg bedrag ⇒ het volle bedrag geboekt."""
    charge = _seed_charge(db_session, amount="10.00")
    edit_payment_record(db_session, charge.id, status="paid", amount_paid=None,
                        actor="fin@test")
    assert charge.status == "paid"
    assert charge.amount_paid == Decimal("10.00")
    assert charge.paid_at is not None


def test_charge_expliciet_deelbedrag(db_session):
    charge = _seed_charge(db_session, amount="10.00")
    edit_payment_record(db_session, charge.id, status="paid",
                        amount_paid=Decimal("4.00"), actor="fin@test")
    assert charge.amount_paid == Decimal("4.00")


def test_charge_bedrag_buiten_grenzen_geweigerd(db_session):
    charge = _seed_charge(db_session, amount="10.00")
    with pytest.raises(ValueError):
        edit_payment_record(db_session, charge.id, status="paid",
                            amount_paid=Decimal("12.00"), actor="fin@test")
    with pytest.raises(ValueError):
        edit_payment_record(db_session, charge.id, status="paid",
                            amount_paid=Decimal("-1.00"), actor="fin@test")


def test_refund_registreer_effectieve_uitbetaling(db_session):
    """Kern van #515: op een (pending) refund de effectief uitbetaalde som boeken.
    De grens is tekengevoelig [amount, 0]; het saldo blijft coherent."""
    charge = _seed_charge(db_session, amount="18.00", amount_paid="18.00", status="paid")
    # Verplichting die nog niet uitbetaald is: amount_paid=None, status=pending.
    refund = create_refund(db_session, charge.id, Decimal("10.00"),
                           actor="fin@test", settled=False)
    assert refund.amount == Decimal("-10.00") and refund.amount_paid is None

    # Effectieve uitbetaling registreren via de unified editor.
    edit_payment_record(db_session, refund.id, status="paid", amount_paid=None,
                        actor="fin@test")
    assert refund.status == "paid"
    assert refund.amount_paid == Decimal("-10.00")  # volledige refund geboekt
    # Netto ontvangen = 18 charge − 10 refund = 8.
    assert net_paid(db_session, "registration", charge.payable_id) == Decimal("8.00")


def test_refund_deeluitbetaling_binnen_grens(db_session):
    charge = _seed_charge(db_session, amount="18.00", amount_paid="18.00", status="paid")
    refund = create_refund(db_session, charge.id, Decimal("10.00"),
                           actor="fin@test", settled=False)
    edit_payment_record(db_session, refund.id, status="paid",
                        amount_paid=Decimal("-6.00"), actor="fin@test")
    assert refund.amount_paid == Decimal("-6.00")
    assert net_paid(db_session, "registration", charge.payable_id) == Decimal("12.00")


def test_refund_bedrag_buiten_grenzen_geweigerd(db_session):
    charge = _seed_charge(db_session, amount="18.00", amount_paid="18.00", status="paid")
    refund = create_refund(db_session, charge.id, Decimal("10.00"),
                           actor="fin@test", settled=False)
    with pytest.raises(ValueError):  # positief bedrag op een negatieve refund
        edit_payment_record(db_session, refund.id, status="paid",
                            amount_paid=Decimal("2.00"), actor="fin@test")
    with pytest.raises(ValueError):  # meer terugbetaald dan de refund groot is
        edit_payment_record(db_session, refund.id, status="paid",
                            amount_paid=Decimal("-15.00"), actor="fin@test")


def test_opmerking_bewaard_en_in_audit(db_session):
    charge = _seed_charge(db_session, amount="10.00")
    edit_payment_record(db_session, charge.id, status="paid", amount_paid=None,
                        note="cash ontvangen aan de kassa", actor="fin@test")
    assert charge.note == "cash ontvangen aan de kassa"
    rows = db_session.query(PaymentRecordHistory).filter(
        PaymentRecordHistory.payment_record_id == charge.id,
    ).all()
    assert any(r.note == "cash ontvangen aan de kassa" for r in rows)


def test_niet_paid_status_zonder_paid_boeking(db_session):
    """status→cancelled (geen bedrag) schrijft enkel de status weg (via snapshot)."""
    charge = _seed_charge(db_session, amount="10.00")
    edit_payment_record(db_session, charge.id, status="cancelled", actor="fin@test")
    assert charge.status == "cancelled"
