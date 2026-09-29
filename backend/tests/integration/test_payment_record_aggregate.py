"""CR-13 phase 2 (#1249): `PaymentRecord` as an aggregate — the B8 tests of its rules.

| what | where it lives now | test below |
|---|---|---|
| the state follows the amounts (#720) | `mark_paid` | transitions, AC6 |
| a charge positive, a refund negative, on a living row | `check()` + CHECK | listener, migration |
| what came in within the amount, on every row | `check()` + CHECK | transitions, migration |
| money came in | `PaymentReceived`, on every way in | once per path |
| a refund to pay out | `RefundDue` | the sweep |
| a membership activated | `membership` on `PaymentReceived` | activation, idempotent |
| a record of nothing removed, not closed on 0,00 | `reconcile_charges` (b) | (b) |

Proven additively (run, removed): the `PaymentReceived` subscription of `membership`
commented out → the activation tests red; `vervroeg_sweep` removed from the workflow
handler → the sweep tests red; the refusal of a wrong sign in the migration is a
test of its own below, on a row written raw.
"""

from __future__ import annotations

import importlib.util
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import text

from app.domains.activities.models import Registration
from app.domains.mdm.api import Member, PaymentMethod
from app.domains.membership.api import Membership
from app.domains.payment.api import (
    PayableType,
    PaymentRecord,
    PaymentRecordHistory,
    PaymentStatus,
    PaymentType,
)
from app.domains.payment.models import PaymentError
from app.domains.payment.service import (
    confirm_manual_payment,
    create_refund,
    handle_gateway_update,
    reconcile_charges,
    registration_balance,
    set_payment_status,
)
from app.kernel import events
from app.kernel.contracts.payment import PaymentReceived
from tests.conftest import seed_activity_with_product

pytestmark = pytest.mark.ui_agnostisch

NOW = datetime(2026, 9, 29, 12, 0, tzinfo=timezone.utc)
MIGRATION = next(
    (Path(__file__).resolve().parents[2] / "alembic" / "versions").glob("171_*payment_record*.py")
)


def _record(amount: str, *, kind=PaymentType.CHARGE, **extra) -> PaymentRecord:
    values = dict(
        payable_type=PayableType.REGISTRATION,
        payable_id=880_001,
        amount=Decimal(amount),
        method=PaymentMethod.TRANSFER,
        status=PaymentStatus.PENDING,
        type=kind,
    )
    values.update(extra)
    return PaymentRecord(**values)


def _stored(db, amount: str, **extra) -> PaymentRecord:
    record = _record(amount, **extra)
    db.add(record)
    db.flush()
    return record


# ── B8 test 7: transitions, without a database ───────────────────────────────


def test_a_partial_payment_stays_partly_paid():
    record = _record("35.00")
    event = record.mark_paid(Decimal("10.00"), at=NOW)
    assert record.status is PaymentStatus.PENDING
    assert record.amount_paid == Decimal("10.00") and record.paid_at == NOW
    assert event.fully_paid is False and event.amount_booked == "10.00"


def test_a_full_payment_is_paid_and_nothing_booked_books_the_full_amount():
    record = _record("35.00")
    event = record.mark_paid(None, at=NOW)
    assert record.status is PaymentStatus.PAID and record.amount_paid == Decimal("35.00")
    assert event.fully_paid is True


def test_a_refund_is_paid_in_full_at_its_most_negative_value():
    record = _record("-5.00", kind=PaymentType.REFUND)
    assert record.mark_paid(Decimal("-5.00"), at=NOW).fully_paid is True
    assert record.status is PaymentStatus.PAID


@pytest.mark.parametrize(
    ("amount", "kind", "booked"),
    [
        ("35.00", PaymentType.CHARGE, "40.00"),
        ("35.00", PaymentType.CHARGE, "-1.00"),
        ("-5.00", PaymentType.REFUND, "-6.00"),
        ("-5.00", PaymentType.REFUND, "1.00"),
    ],
)
def test_booking_beyond_the_amount_is_refused(amount, kind, booked):
    record = _record(amount, kind=kind)
    with pytest.raises(PaymentError, match="moet tussen"):
        record.mark_paid(Decimal(booked), at=NOW)
    assert record.amount_paid is None, "a refused booking wrote something"


def test_cancel_forgets_what_came_in_and_cannot_mean_paid():
    record = _record("35.00", amount_paid=Decimal("35.00"), status=PaymentStatus.PAID)
    record.cancel(PaymentStatus.CANCELLED)
    assert (record.status, record.amount_paid, record.paid_at) == (
        PaymentStatus.CANCELLED,
        None,
        None,
    )
    with pytest.raises(PaymentError, match="mark_paid"):
        record.cancel(PaymentStatus.PAID)


@pytest.mark.parametrize(
    ("amount", "kind", "message"),
    [
        ("0.00", PaymentType.CHARGE, "positief"),
        ("-1.00", PaymentType.CHARGE, "positief"),
        ("0.00", PaymentType.REFUND, "negatief"),
        ("10.00", PaymentType.REFUND, "negatief"),
    ],
)
def test_check_refuses_the_wrong_sign(amount, kind, message):
    with pytest.raises(PaymentError, match=message):
        _record(amount, kind=kind).check()


# ── The listener: the record says no on flush, without a call ─────────────────


def test_a_charge_of_nothing_is_refused_at_flush(db_session):
    db_session.add(_record("0.00"))
    with pytest.raises(PaymentError, match="positief"):
        db_session.flush()


# ── AC6 / #720 on the treasurer's status correction ───────────────────────────


def test_setting_a_partly_paid_record_to_paid_leaves_it_partly_paid(db_session):
    """AC6: the state follows the amounts, not the action. Before phase 2 the status
    correction set "paid" on € 10,00 of € 35,00 — the one path #720 had not reached."""
    record = _stored(db_session, "35.00", amount_paid=Decimal("10.00"), paid_at=NOW)
    set_payment_status(db_session, record.id, "paid", actor="penningmeester@example.com")
    assert record.status is PaymentStatus.PENDING
    assert record.amount_paid == Decimal("10.00")
    assert record.state() == "partial"


# ── PaymentReceived: exactly once, on every way money comes in ────────────────


@pytest.fixture
def received(monkeypatch):
    seen: list[PaymentReceived] = []
    events.subscribe(PaymentReceived)(lambda event, db: seen.append(event))
    yield seen
    events._subscribers[PaymentReceived].pop()


def test_the_webhook_publishes_once_even_when_it_arrives_twice(db_session, received):
    from app.domains.payment.api import GatewayPayment

    gateway = GatewayPayment(provider="stub", provider_payment_id="st_1", amount=Decimal("10"))
    db_session.add(gateway)
    db_session.flush()
    record = _stored(
        db_session, "10.00", method=PaymentMethod.ONLINE, gateway_payment_id=gateway.id
    )
    handle_gateway_update(db_session, gateway.id, "paid")
    handle_gateway_update(db_session, gateway.id, "paid")
    assert [(e.payment_record_id, e.fully_paid) for e in received] == [(record.id, True)]


def test_a_manual_confirmation_publishes_once(db_session, received):
    record = _stored(db_session, "20.00")
    confirm_manual_payment(db_session, record.id, actor="penningmeester@example.com")
    assert [(e.payment_record_id, e.amount_booked, e.source) for e in received] == [
        (record.id, "20.00", "admin_manual")
    ]


def test_a_status_correction_to_paid_publishes_once(db_session, received):
    record = _stored(db_session, "20.00")
    set_payment_status(db_session, record.id, "paid")
    set_payment_status(db_session, record.id, "cancelled")
    assert [e.payment_record_id for e in received] == [record.id]


# ── membership activates on the event — in full only, and once ────────────────


def _membership(db, *, active=False) -> Membership:
    member = Member()
    db.add(member)
    db.flush()
    membership = Membership(member_id=member.id, year=2026, is_active=active)
    db.add(membership)
    db.flush()
    return membership


def test_a_membership_is_activated_by_its_full_payment(db_session):
    membership = _membership(db_session)
    record = _stored(
        db_session, "30.00", payable_type=PayableType.MEMBERSHIP, payable_id=membership.id
    )
    confirm_manual_payment(db_session, record.id)
    assert membership.is_active and membership.valid_from and membership.valid_to


def test_a_partial_payment_does_not_activate_a_membership(db_session):
    """#720: the rest is still owed."""
    membership = _membership(db_session)
    record = _stored(
        db_session, "30.00", payable_type=PayableType.MEMBERSHIP, payable_id=membership.id
    )
    confirm_manual_payment(db_session, record.id, amount_paid=Decimal("10.00"))
    assert not membership.is_active


def test_the_same_event_twice_activates_once(db_session):
    """§B4.1: the provider's webhook can arrive twice; one activation, one history row."""
    from app.domains.membership.models import MembershipHistory

    membership = _membership(db_session)
    event = PaymentReceived(
        payment_record_id="x",
        payable_type="membership",
        payable_id=membership.id,
        amount_booked="30.00",
        fully_paid=True,
        method="transfer",
        source="mollie",
    )
    events.publish(event, db_session)
    events.publish(event, db_session)
    assert membership.is_active
    rows = (
        db_session.query(MembershipHistory)
        .filter(
            MembershipHistory.membership_id == membership.id,
            MembershipHistory.action == "membership_activated",
        )
        .count()
    )
    assert rows == 1


# ── The sweep: advanced on money and on a refund to pay out ──────────────────


@pytest.fixture
def sweeps(monkeypatch):
    from app.domains.workflow import api as workflow_api

    calls: list[str] = []
    monkeypatch.setattr(workflow_api, "vervroeg_sweep", lambda db: calls.append("sweep"))
    return calls


def test_a_refund_to_pay_out_advances_the_sweep(db_session, sweeps):
    charge = _stored(db_session, "20.00", amount_paid=Decimal("20.00"), paid_at=NOW)
    create_refund(db_session, charge.id, Decimal("5.00"), settled=False)
    assert sweeps == ["sweep"]


def test_a_payment_advances_the_sweep_on_every_way_in(db_session, sweeps):
    """B7.1, a named difference in timing (master CLI, 29 September 2026): a Mollie
    payment advances the sweep too — the same tasks, seen sooner."""
    record = _stored(db_session, "20.00")
    confirm_manual_payment(db_session, record.id, amount_paid=Decimal("5.00"))
    assert sweeps == ["sweep"]


# ── (b): a record of nothing is removed, not closed on 0,00 ──────────────────


@pytest.mark.parametrize(
    ("amount", "kind"), [("20.00", PaymentType.CHARGE), ("-5.00", PaymentType.REFUND)]
)
def test_reconcile_removes_a_record_on_which_nothing_came_in(db_session, amount, kind):
    """#1249 (b): closed on 0,00 it would break the sign rule; removed, it keeps its
    amount and leaves a history row."""
    record = _stored(db_session, amount, kind=kind, amount_paid=Decimal("0.00"))
    reconcile_charges(db_session, PayableType.REGISTRATION, 880_001, Decimal("0"))
    assert record.deleted_at is not None
    assert record.amount == Decimal(amount), "the amount was changed"
    history = (
        db_session.query(PaymentRecordHistory)
        .filter(PaymentRecordHistory.payment_record_id == record.id)
        .all()
    )
    assert [(h.operation, h.action) for h in history] == [("delete", "order_reconciled")]


# ── The migration: clean up what it can, refuse what it cannot ────────────────


def _migration():
    spec = importlib.util.spec_from_file_location("migration_171", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _without_the_sign_rule(db):
    connection = db.connection()
    connection.execute(
        text("ALTER TABLE payment.payment_records DROP CONSTRAINT ck_payment_records_sign")
    )
    return connection


def test_the_migration_removes_a_charge_of_nothing_with_a_history_row(db_session):
    """Proof, additive: the sign rule dropped inside the test's transaction, a living
    charge of 0,00 written raw — the migration soft-deletes it, keeps its amount and
    writes `zero_charge_removed`."""
    connection = _without_the_sign_rule(db_session)
    record = _stored(db_session, "10.00")
    connection.execute(
        text("UPDATE payment.payment_records SET amount = 0 WHERE id = :id"), {"id": record.id}
    )
    migration = _migration()
    assert migration.data_check(connection) == []
    assert migration.remove_zero_records(connection) == 1
    row = connection.execute(
        text("SELECT amount, deleted_at FROM payment.payment_records WHERE id = :id"),
        {"id": record.id},
    ).one()
    assert row.amount == 0 and row.deleted_at is not None
    action = connection.execute(
        text(
            "SELECT action, source FROM payment.payment_record_history "
            "WHERE payment_record_id = :id AND action = 'zero_charge_removed'"
        ),
        {"id": record.id},
    ).one()
    assert tuple(action) == ("zero_charge_removed", "migration")


def test_the_migration_refuses_a_wrong_sign_it_cannot_fix(db_session):
    from alembic.operations import Operations
    from alembic.runtime.migration import MigrationContext

    connection = _without_the_sign_rule(db_session)
    record = _stored(db_session, "10.00")
    connection.execute(
        text("UPDATE payment.payment_records SET amount = -3 WHERE id = :id"), {"id": record.id}
    )
    migration = _migration()
    assert migration.data_check(connection) == ["1 living payment record(s) with the wrong sign"]
    with Operations.context(MigrationContext.configure(connection)):
        with pytest.raises(migration.DataCheckFailed, match="wrong sign"):
            migration.upgrade()


# ── The balance: the owner and the report's view agree ───────────────────────


def test_the_balance_equals_the_open_amount_of_the_report(client, db_session):
    """§B4.3, AC5, phase 2: `registration_balance` owns the balance; the report
    computes it in SQL. After a partial payment and an order change, both agree."""
    _activity, component, product = seed_activity_with_product(db_session, price="12.00")
    response = client.post(
        f"/api/v1/activities/{component.activity_id}/register",
        json={
            "contact_name": "Saldo Pariteit",
            "contact_email": "saldo@example.org",
            "phone": "0470000000",
            "payment_method": "transfer",
            "component_id": component.id,
            "items": [{"product_id": product.id, "quantity": 3}],
        },
    )
    assert response.status_code in (200, 201), response.text
    registration = db_session.get(Registration, response.json()["id"])
    charge = (
        db_session.query(PaymentRecord)
        .filter(PaymentRecord.payable_id == registration.id)
        .filter(PaymentRecord.payable_type == PayableType.REGISTRATION)
        .one()
    )
    confirm_manual_payment(db_session, charge.id, amount_paid=Decimal("20.00"))
    db_session.flush()

    owner = registration_balance(db_session, registration)["balance"]
    view = db_session.execute(
        text(
            "SELECT COALESCE(SUM(open_amount), 0) FROM reporting.f_payments "
            "WHERE payable_type = 'registration' AND payable_id = :id"
        ),
        {"id": registration.id},
    ).scalar()
    assert owner == Decimal("16.00")
    assert Decimal(view) == owner, f"registration {registration.id}: owner {owner}, view {view}"


def test_a_date_is_not_needed_to_ask():
    """The aggregate's methods read what they carry: no session, no date lookup."""
    record = _record("12.00")
    record.mark_paid(None, at=datetime(2026, 1, 1, tzinfo=timezone.utc))
    assert record.state() == "paid" and date(2026, 1, 1) == record.paid_at.date()
