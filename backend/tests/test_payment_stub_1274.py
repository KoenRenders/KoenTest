"""The stub payment provider and its brake (#1274).

A stand-in for Mollie lets the e2e tests walk the online payment chain. The same
stand-in on UAT or PROD would mark registrations paid without money — the worst
thing this codebase can do. So the stub and its brake come in one change, and
the brake is proven in both directions:

- **too loose** and the stub is reachable on PROD. Refused at start-up
  (`Settings`), refused when a provider is chosen (`_get_provider`), and its
  pretend checkout page and webhook are never registered there;
- **misplaced** and real Mollie payments break. `_get_provider` runs for every
  real payment and every status re-fetch, so the test that the stub is refused
  on PROD also checks that Mollie comes out of the same function untouched.

And the stub has to be able to say something else than "paid": it starts at
*open*, so a webhook before the pretend payment must leave the record pending.

Broken on purpose (28 September 2026), one violation at a time:

| Violation | Failed |
|---|---|
| the start-up check in `Settings` switched off | the three "does not start" tests (prod, uat, hdev) |
| the check in the stub branch of `_get_provider` switched off | "on prod the stub is refused" |
| the check moved in front of every provider (misplaced) | the same test — on its Mollie half |
| `app.main` registering the stub routes always | "the real app asks the settings" |
| the stub starting at *paid* | "a webhook before the payment leaves the record pending" |
"""
import importlib
from decimal import Decimal

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.config import PAYMENT_STUB_ENVIRONMENTS, Settings, settings
from app.domains.payment.api import PayableType, create_payment_record
from app.domains.payment.gateway_service import StubRefused, _get_provider
from app.domains.payment.models import PaymentProvider, PaymentStatus
from app.domains.payment.providers.mollie import MollieProvider
from app.domains.payment.providers.stub import StubProvider

STRONG_KEY = "x" * 64
STUB_PATH = "/api/v1/payment-gateway/webhooks/stub"


# ── The brake at start-up ─────────────────────────────────────────────────────

@pytest.mark.parametrize("env", ["prod", "uat", "hdev"])
def test_the_stub_does_not_start_outside_development(env):
    with pytest.raises(ValueError, match="PAYMENT_PROVIDER=stub"):
        Settings(app_env=env, payment_provider="stub", secret_key=STRONG_KEY)


@pytest.mark.parametrize("env", PAYMENT_STUB_ENVIRONMENTS)
def test_the_stub_starts_in_development_and_the_tests(env):
    assert Settings(app_env=env, payment_provider="stub",
                    secret_key=STRONG_KEY).payment_stub_allowed


def test_mollie_starts_on_prod():
    """The other side of the start-up brake: it may not catch the real one."""
    assert Settings(app_env="prod", payment_provider="mollie",
                    secret_key=STRONG_KEY).payment_provider == "mollie"


# ── The brake when a provider is chosen ───────────────────────────────────────

def test_on_prod_the_stub_is_refused_and_mollie_is_untouched(monkeypatch):
    """One function, both directions — the brake sits in the stub's branch."""
    monkeypatch.setattr(settings, "app_env", "prod")
    with pytest.raises(StubRefused):
        _get_provider(PaymentProvider.STUB)
    assert isinstance(_get_provider(PaymentProvider.MOLLIE, api_key="test_x"), MollieProvider)


def test_in_the_tests_the_stub_is_chosen(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "test")
    assert isinstance(_get_provider(PaymentProvider.STUB), StubProvider)


# ── The stub's pages exist only where the stub may ────────────────────────────

def test_the_stub_routes_are_not_registered_where_the_stub_is_refused():
    from app.domains.payment.stub_router import include_stub_routes

    closed, open_ = FastAPI(), FastAPI()
    assert include_stub_routes(closed, allowed=False) is False
    assert include_stub_routes(open_, allowed=True) is True
    for app, expected in ((closed, 404), (open_, 200)):
        answer = TestClient(app).post(STUB_PATH, data={"id": "stub_unknown"})
        # 200 is the webhook answering "ignored" for an id it does not know.
        assert answer.status_code == expected, (app is closed, answer.status_code)


def test_the_real_app_asks_the_settings_whether_to_register_them(monkeypatch):
    """The wiring, not only the function: `app.main` built with a PROD setting
    has no stub webhook, built with the test setting it has one. Rebuilt by
    reloading the module; the original is restored afterwards."""
    import app.main as main_module

    try:
        monkeypatch.setattr(settings, "app_env", "prod")
        prod_app = importlib.reload(main_module).app
        assert TestClient(prod_app).post(STUB_PATH, data={"id": "x"}).status_code == 404
        monkeypatch.setattr(settings, "app_env", "test")
        test_app = importlib.reload(main_module).app
        assert TestClient(test_app).post(STUB_PATH, data={"id": "x"}).status_code == 200
    finally:
        monkeypatch.undo()
        importlib.reload(main_module)


# ── The stub starts at open, and the webhook re-fetches ───────────────────────

def test_a_webhook_before_the_payment_leaves_the_record_pending(db_session, monkeypatch):
    """The point of the stub: it can say something else than the webhook body.
    Its webhook carries only the id; the status comes from the stub, and the
    stub says *paid* only after the pretend checkout page recorded a payment."""
    from app.domains.payment.gateway_router import process_webhook
    from app.domains.payment.models import GatewayPayment, PaymentRecord
    from app.domains.payment.providers import stub

    monkeypatch.setattr(settings, "app_env", "test")
    monkeypatch.setattr(settings, "payment_provider", "stub")
    record = create_payment_record(db_session, payable_type=PayableType.MEMBERSHIP,
                                   payable_id=7, amount=Decimal("15.00"), method="online",
                                   redirect_url="https://example.org/terug",
                                   description="Lidgeld")
    gp = db_session.get(GatewayPayment, record.gateway_payment_id)
    assert gp.provider is PaymentProvider.STUB
    assert gp.checkout_url.startswith(stub.CHECKOUT_PATH + "/")

    process_webhook(db_session, gp.provider_payment_id)
    db_session.refresh(record)
    assert record.status is PaymentStatus.PENDING, "paid before anyone paid"

    stub.pay(gp.provider_payment_id)
    process_webhook(db_session, gp.provider_payment_id)
    db_session.refresh(record)
    assert db_session.get(PaymentRecord, record.id).status is PaymentStatus.PAID
