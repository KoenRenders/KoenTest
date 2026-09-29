"""CR-13 phase 1: an order change reaches payment through `OrderChanged` (§B4.9).

Until phase 1 activities called `payment.api.reconcile_registration_charges`
itself, after a commit — so a reconciliation that failed left the order lines
changed and the balance behind (B4.1, measured on 27 September 2026). Now the
service publishes `OrderChanged` and payment's handler reconciles in the same
transaction, before the one commit.

What stays the same (R13, AC8): the charges follow the order exactly as before —
the existing reconciliation tests (`test_reconcile_charges.py`,
`test_registration_delete.py`) run unchanged. What changes is the one failure
path B7.1 names, and the test below shows the old failure can no longer occur.

Proven additively (run, removed): the old mid-way `db.commit()` put back in
`delete_registration`, before the reconciliation → the failure-path test red, "the
lines were committed before the reconciliation ran", and the one-commit test with
it. The refusal to publish into silence is a test of its own below.
"""

from __future__ import annotations

import pytest

from app.domains.activities import service
from app.domains.activities.api import Registration
from app.domains.payment import handlers as payment_handlers
from app.domains.payment.api import PayableType, PaymentRecord
from app.kernel import events
from app.kernel.contracts.activities import OrderChanged
from tests.conftest import seed_activity_with_product


def _register(client, db_session, quantity=2, price="18.00"):
    _activity, component, product = seed_activity_with_product(db_session, price=price)
    response = client.post(
        f"/api/v1/activities/{component.activity_id}/register",
        json={
            "contact_name": "An Janssens",
            "contact_email": "an@example.org",
            "phone": "0470000000",
            "payment_method": "transfer",
            "component_id": component.id,
            "items": [{"product_id": product.id, "quantity": quantity}],
        },
    )
    assert response.status_code in (200, 201), response.text
    registration = db_session.get(Registration, response.json()["id"])
    return component, registration


def _charges(db_session, registration_id):
    return (
        db_session.query(PaymentRecord)
        .filter(
            PaymentRecord.payable_type == PayableType.REGISTRATION,
            PaymentRecord.payable_id == registration_id,
        )
        .all()
    )


def test_the_event_reaches_payment(client, db_session):
    """An order line lowered → the event carries the new total, the handler brings
    the open charge to it."""
    component, registration = _register(client, db_session, quantity=2)
    line = registration.items[0]

    seen: list[OrderChanged] = []
    events.subscribe(OrderChanged)(lambda event, db: seen.append(event))
    try:
        service.update_order_line(
            db_session,
            component.activity_id,
            registration.id,
            line.id,
            product_id=line.product_id,
            quantity=1,
            actor="beheerder@example.com",
        )
    finally:
        events._subscribers[OrderChanged].pop()

    assert [(e.registration_id, e.total_due, e.actor) for e in seen] == [
        (registration.id, "18.00", "beheerder@example.com")
    ]
    open_amounts = sorted(str(r.amount) for r in _charges(db_session, registration.id))
    assert open_amounts == ["18.00"], open_amounts


def test_a_failing_reconciliation_leaves_the_order_as_it_was(client, db_session, monkeypatch):
    """The failure path that changes (B7.1): before phase 1, deleting a registration
    COMMITTED the deleted lines and only then reconciled — a failure there left the
    lines gone and the balance wrong. Now nothing is committed before the
    reconciliation: when it raises, not one commit has happened, so the deleted
    lines exist only in the transaction the request loses."""
    component, registration = _register(client, db_session, quantity=2)
    commits: list[str] = []
    monkeypatch.setattr(db_session, "commit", lambda: commits.append("commit"))

    def failing(event, db):
        raise RuntimeError("reconciliation failed")

    handlers = events._subscribers[OrderChanged]
    original = list(handlers)
    handlers[:] = [failing]
    try:
        with pytest.raises(RuntimeError, match="reconciliation failed"):
            service.delete_registration(
                db_session, component.activity_id, registration.id, actor="beheerder@example.com"
            )
    finally:
        handlers[:] = original
    assert commits == [], "the lines were committed before the reconciliation ran"


def test_deleting_a_registration_commits_once(client, db_session, monkeypatch):
    """The other direction: with payment reconciling, the deletion is one commit —
    lines, reconciliation and the registration together (§B4.1)."""
    component, registration = _register(client, db_session, quantity=2)
    real_commit = db_session.commit
    commits: list[str] = []

    def counting_commit():
        commits.append("commit")
        real_commit()

    monkeypatch.setattr(db_session, "commit", counting_commit)
    assert service.delete_registration(
        db_session, component.activity_id, registration.id, actor="beheerder@example.com"
    )
    assert commits == ["commit"]
    assert _charges(db_session, registration.id) == [], "the unpaid charge was not reconciled"


def test_an_order_change_is_not_published_into_silence(client, db_session):
    """With payment's handler not registered, the service refuses rather than leave
    the balance behind without a trace (#185)."""
    component, registration = _register(client, db_session, quantity=2)
    line = registration.items[0]
    handlers = events._subscribers[OrderChanged]
    original = list(handlers)
    handlers.clear()
    try:
        with pytest.raises(RuntimeError, match="no subscriber"):
            service.update_order_line(
                db_session,
                component.activity_id,
                registration.id,
                line.id,
                product_id=line.product_id,
                quantity=1,
                actor=None,
            )
    finally:
        handlers[:] = original
    assert payment_handlers.reconcile_registration_on_order_change in handlers
