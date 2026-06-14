"""Betalings-hardening (defense-in-depth):

- #92: bij status-refresh naar 'paid' moet het door de provider gerapporteerde
  bedrag/valuta overeenkomen met het verwachte (gateway_payments.amount, EUR).
  Bij een mismatch wordt NIET als betaald gemarkeerd, maar gemarkeerd voor controle.
- #91: één gateway-betaling kan maar één PaymentRecord backen (DB-unieke index).
"""
from decimal import Decimal

from app.domains.payment_gateway.providers.base import PaymentStatusResult


def _seed_gateway_payment(db, amount="35.00", status="pending"):
    from app.domains.payment_gateway.models import GatewayPayment
    gp = GatewayPayment(
        provider="mollie",
        provider_payment_id="tr_test_123",
        amount=Decimal(amount),
        status=status,
        checkout_url="https://mollie.test/checkout/tr_test_123",
        description="Test",
        payment_metadata={},
    )
    db.add(gp)
    db.flush()
    return gp


def test_amount_mismatch_blocks_paid(db_session, monkeypatch):
    """Provider meldt 'paid' maar met een te laag bedrag → status wordt
    'needs_review', niet 'paid'."""
    from app.domains.payment_gateway.providers import mollie
    from app.domains.payment_gateway.service import refresh_payment_status

    gp = _seed_gateway_payment(db_session, amount="35.00")
    monkeypatch.setattr(
        mollie.MollieProvider, "get_payment_details",
        lambda self, pid: PaymentStatusResult(status="paid", amount=Decimal("5.00"), currency="EUR"),
    )

    refreshed = refresh_payment_status(db_session, gp.id)
    assert refreshed.status == "needs_review"


def test_wrong_currency_blocks_paid(db_session, monkeypatch):
    from app.domains.payment_gateway.providers import mollie
    from app.domains.payment_gateway.service import refresh_payment_status

    gp = _seed_gateway_payment(db_session, amount="35.00")
    monkeypatch.setattr(
        mollie.MollieProvider, "get_payment_details",
        lambda self, pid: PaymentStatusResult(status="paid", amount=Decimal("35.00"), currency="USD"),
    )

    refreshed = refresh_payment_status(db_session, gp.id)
    assert refreshed.status == "needs_review"


def test_matching_amount_marks_paid(db_session, monkeypatch):
    from app.domains.payment_gateway.providers import mollie
    from app.domains.payment_gateway.service import refresh_payment_status

    gp = _seed_gateway_payment(db_session, amount="35.00")
    monkeypatch.setattr(
        mollie.MollieProvider, "get_payment_details",
        lambda self, pid: PaymentStatusResult(status="paid", amount=Decimal("35.00"), currency="EUR"),
    )

    refreshed = refresh_payment_status(db_session, gp.id)
    assert refreshed.status == "paid"


def test_gateway_payment_id_is_unique_on_payment_records(db_session):
    """#91: een tweede PaymentRecord met dezelfde gateway_payment_id wordt door de
    DB-unieke index geweigerd."""
    import pytest
    from sqlalchemy.exc import IntegrityError
    from app.domains.payment_status.models import PaymentRecord

    gp = _seed_gateway_payment(db_session)
    db_session.add(PaymentRecord(
        payable_type="membership", payable_id=1, amount=Decimal("35.00"),
        method="online", status="pending", gateway_payment_id=gp.id,
    ))
    db_session.flush()
    db_session.add(PaymentRecord(
        payable_type="membership", payable_id=2, amount=Decimal("35.00"),
        method="online", status="pending", gateway_payment_id=gp.id,
    ))
    with pytest.raises(IntegrityError):
        db_session.flush()
