"""The treasurer's "Ververs" books a payment the gateway reports as paid (#1249).

A regression test for a bug that lived from CR-12 phase 1 to CR-13 phase 2:
`refresh_record_status` looked up the gateway's status — a plain string — in
`_GATEWAY_ACTION`, which is keyed by `PaymentStatus` members. A string is never a
member, so the lookup was always false and the refresh applied nothing: the
button answered, the record stayed open. No test ran the refresh with a gateway
that says *paid* and then looked at the record.

Both ways in are covered, because both now ask the same service function: the
screen (`/admin/betalingen/{id}/verversen`) and the JSON route
(`/api/v1/payment-status/records/{id}/refresh`). The gateway is the stub provider
(#1274), so the amount check of #92 runs on a real amount instead of being skipped.

**Writing these tests found a second bug under the first.** With the comparison
repaired, the refresh did book the payment — `PaymentReceived` went out — and then
`db.refresh(record)` reloaded the row and threw the unflushed booking away. The
existing JSON test did not see it: it pays a *membership*, whose subscriber queries
and so autoflushes first. A registration has no such subscriber. These tests use a
registration; on master `4cf4ac13` both "paid" tests failed with the event
published and the record still open.

Broken on purpose to check that these tests can go red: in `refresh_record_status`
one line was added after the conversion, `status = gp.status`, which puts the old
comparison (the gateway's string against the enum keys) back. Both "paid" tests
then fail on the record's status; the "open" test stays green, as it should — it
guards the other direction.
"""

from decimal import Decimal

import pytest

from app.config import settings
from app.domains.auth.api import SESSION_COOKIE, User, UserRole, csrf_token_for, make_session_value
from app.domains.payment.api import GatewayPayment, PaymentRecord, PaymentStatus
from app.domains.payment.providers import stub
from app.kernel.contracts.payment import PaymentReceived
from app.kernel.events import _subscribers, subscribe
from tests.conftest import SEEDED_ADMIN_EMAIL

pytestmark = pytest.mark.ui_serverrendered


@pytest.fixture
def received(monkeypatch):
    """Every `PaymentReceived` published during the test."""
    monkeypatch.setattr(settings, "app_env", "test")
    seen: list[PaymentReceived] = []

    def _handler(event, db):
        seen.append(event)

    subscribe(PaymentReceived)(_handler)
    yield seen
    _subscribers[PaymentReceived].remove(_handler)


def _finance(db):
    user = db.query(User).filter(User.email == SEEDED_ADMIN_EMAIL).first()
    if not any(r.role_code.value == "FINANCE" for r in user.roles):
        db.add(UserRole(user_id=user.id, role_code="FINANCE"))
    db.flush()


def _screen_headers(client, db):
    _finance(db)
    value = make_session_value(SEEDED_ADMIN_EMAIL)
    client.cookies.set(SESSION_COOKIE, value)
    return {"X-CSRF-Token": csrf_token_for(value)}


def _online_charge(db, *, at_gateway: PaymentStatus, payable_id: int) -> PaymentRecord:
    """An open online charge of 25,00 whose stub payment stands at `at_gateway`."""
    provider_id = f"stub_refresh_{payable_id}"
    stub.PAYMENTS[provider_id] = stub.StubPayment(
        amount=Decimal("25.00"),
        redirect_url="/",
        webhook_url="/",
        status=at_gateway,
    )
    gateway = GatewayPayment(
        provider="stub",
        provider_payment_id=provider_id,
        amount=Decimal("25.00"),
        status="pending",
        payment_metadata={},
    )
    db.add(gateway)
    db.flush()
    record = PaymentRecord(
        payable_type="registration",
        payable_id=payable_id,
        amount=Decimal("25.00"),
        method="online",
        status="pending",
        type="charge",
        gateway_payment_id=gateway.id,
    )
    db.add(record)
    db.flush()
    return record


def _reread(db, record_id) -> PaymentRecord:
    db.expire_all()
    return db.query(PaymentRecord).filter(PaymentRecord.id == record_id).one()


def _assert_paid_once(record: PaymentRecord, received: list[PaymentReceived]) -> None:
    assert record.status == PaymentStatus.PAID, (
        "the gateway says paid and the record is still open — the refresh applied nothing"
    )
    assert record.amount_paid == record.amount == Decimal("25.00")
    assert record.paid_at is not None
    assert [e.payment_record_id for e in received] == [record.id], (
        f"expected one PaymentReceived for this record, got {received}"
    )
    assert received[0].fully_paid is True


def test_the_screen_refresh_books_what_the_gateway_calls_paid(client, db_session, received):
    headers = _screen_headers(client, db_session)
    record = _online_charge(db_session, at_gateway=PaymentStatus.PAID, payable_id=12491)

    resp = client.post(f"/admin/betalingen/{record.id}/verversen", headers=headers)

    assert resp.status_code == 200, resp.text[:300]
    _assert_paid_once(_reread(db_session, record.id), received)


def test_the_json_refresh_books_what_the_gateway_calls_paid(
    client, db_session, admin_headers, received
):
    _finance(db_session)
    record = _online_charge(db_session, at_gateway=PaymentStatus.PAID, payable_id=12492)

    resp = client.post(f"/api/v1/payment-status/records/{record.id}/refresh", headers=admin_headers)

    assert resp.status_code == 200, resp.text[:300]
    _assert_paid_once(_reread(db_session, record.id), received)


def test_a_payment_still_open_at_the_gateway_stays_open(client, db_session, received):
    """The other direction: without it, a refresh that books everything would pass."""
    headers = _screen_headers(client, db_session)
    record = _online_charge(db_session, at_gateway=PaymentStatus.PENDING, payable_id=12493)

    resp = client.post(f"/admin/betalingen/{record.id}/verversen", headers=headers)

    assert resp.status_code == 200, resp.text[:300]
    after = _reread(db_session, record.id)
    assert after.status == PaymentStatus.PENDING
    assert not after.amount_paid
    assert after.paid_at is None
    assert received == []
