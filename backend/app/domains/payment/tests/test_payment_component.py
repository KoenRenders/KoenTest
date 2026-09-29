"""Fase 3 (#401): payment-component — het betaal-event en idempotente
webhook-afhandeling (§19.2). Since CR-13 phase 2 the event is `PaymentReceived`;
`PaymentSettled`, which only the webhook published, is gone.

De wees-record-reconciliatie stond hier ook. Die is met #824 verdwenen: een
wees-betaling is geen gebeurtenis in het bedrijf maar een symptoom van een bug, en
sinds #667 kan de applicatie er geen meer maken. Wat ervan overblijft is een
invariant in de TESTS (`_invarianten.assert_geen_wezen`) — voorkomen in plaats van
signaleren.
"""

from decimal import Decimal

from app.domains.payment.api import GatewayPayment, PaymentRecord, handle_gateway_update
from app.kernel.contracts.payment import PaymentReceived
from app.kernel.events import _subscribers, subscribe


def _gateway_payment(db, amount="10.00"):
    gp = GatewayPayment(provider="mollie", provider_payment_id="tr_x", amount=Decimal(amount))
    db.add(gp)
    db.flush()
    return gp


def _record(db, gp=None, payable_type="registration", payable_id=999_999, amount="10.00"):
    rec = PaymentRecord(
        payable_type=payable_type,
        payable_id=payable_id,
        amount=Decimal(amount),
        method="online",
        gateway_payment_id=gp.id if gp else None,
    )
    db.add(rec)
    db.flush()
    return rec


def test_payment_received_published_once_for_repeated_webhook(db_session):
    seen = []

    def _handler(event, db):
        seen.append(event)

    subscribe(PaymentReceived)(_handler)
    try:
        gp = _gateway_payment(db_session)
        rec = _record(db_session, gp)
        handle_gateway_update(db_session, gateway_payment_id=gp.id, new_status="paid")
        # Herhaalde webhook: no-op — geen tweede event, paid_at blijft staan.
        eerste_paid_at = rec.paid_at
        handle_gateway_update(db_session, gateway_payment_id=gp.id, new_status="paid")
        assert len(seen) == 1
        assert seen[0].payment_record_id == rec.id and seen[0].amount_booked == "10.00"
        assert seen[0].fully_paid is True
        assert rec.paid_at == eerste_paid_at and rec.amount_paid == Decimal("10.00")
    finally:
        _subscribers[PaymentReceived].remove(_handler)
