"""The webhook URL Mollie is given is a route that exists (#1279).

Since #1178 the provider name is a `PaymentProvider` member, and
`gateway_service.create_payment` put it straight into an f-string. A plain Enum
formats as `PaymentProvider.MOLLIE`, so every online payment on master handed
Mollie `…/webhooks/PaymentProvider.MOLLIE` — a URL that answered 404, while the
route is `…/webhooks/mollie`. Nothing failed: Mollie simply could not tell us a
payment was paid. Measured on HDEV before the fix: no online payment had been
created since CR-12 arrived there, so none was hit.

The same shape — a member where a code used to be — broke two templates in
#1268; this is the first place where money hung on it. An AST scan of `app/`
for f-strings, `str()` and `.format()` on a code-list member found one more:
the payment description's fallback, `f"{payable_type} #{payable_id}"`, which
every online caller happens to bypass with its own description today.

Broken on purpose (28 September 2026): both lines set back to the member in the
f-string → both tests failed, one on
`http://localhost:8000/api/v1/payment-gateway/webhooks/PaymentProvider.MOLLIE`,
the other on `PayableType.MEMBERSHIP #6`.
"""
from decimal import Decimal

from app.domains.payment.api import PayableType, create_payment_record


def _capture(monkeypatch) -> dict:
    from app.domains.payment.providers import mollie
    from app.domains.payment.providers.base import PaymentResult

    seen: dict = {}

    def fake_create_payment(self, amount, description, redirect_url, webhook_url, metadata):
        seen.update(description=description, webhook_url=webhook_url)
        return PaymentResult(provider_payment_id="tr_1279", status="pending",
                             checkout_url="https://mollie.test/checkout/tr_1279")

    monkeypatch.setattr(mollie.MollieProvider, "create_payment", fake_create_payment)
    return seen


def test_mollie_is_given_the_webhook_route_that_exists(client, db_session, monkeypatch):
    """Two halves: the URL is the one we expect, and that URL answers. The
    second half is what makes the first mean something — Mollie does not read
    our route table, it POSTs to whatever it was given."""
    from urllib.parse import urlsplit

    seen = _capture(monkeypatch)
    create_payment_record(db_session, payable_type=PayableType.MEMBERSHIP, payable_id=5,
                          amount=Decimal("10.00"), method="online",
                          redirect_url="https://example.org/terug", description="Lidgeld")
    path = urlsplit(seen["webhook_url"]).path
    assert path == "/api/v1/payment-gateway/webhooks/mollie", seen["webhook_url"]
    # The webhook is rate-limited per client, and earlier tests in the run used
    # the budget: a 429 here is the limiter, not a missing route. Cleared the way
    # `test_kritische_flows_security.py` clears it.
    from app.limiter import mollie_webhook_limiter

    mollie_webhook_limiter._calls.clear()
    answer = client.post(path, data={"id": "tr_unknown_1279"})
    assert answer.status_code == 200 and answer.json() == {"status": "ignored"}, (
        f"Mollie's POST to {path} would get {answer.status_code}")


def test_the_fallback_description_carries_the_code(db_session, monkeypatch):
    seen = _capture(monkeypatch)
    create_payment_record(db_session, payable_type=PayableType.MEMBERSHIP, payable_id=6,
                          amount=Decimal("10.00"), method="online",
                          redirect_url="https://example.org/terug")
    assert seen["description"] == f"{PayableType.MEMBERSHIP.value} #6", seen["description"]
