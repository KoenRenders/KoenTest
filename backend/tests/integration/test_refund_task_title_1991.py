"""#1991 — a refund task names the payment in words.

Koen saw on HDEV (14 October 2026) a task titled "Refund a6574dd9-… bevestigen
(membership #77)": the record's id, an English word and a code. The title
now names the payable by its label from payment's own code list, with its
number — "Terugbetaling lidmaatschap #77 bevestigen" — and no id; the id
stays the task's subject.

The title is stored with the task and is the sweep's key: an open task made
under the old title would be closed as if its cause were gone, and a new one
opened beside it. So the sweep gives an open task of its own kinds whose
cause is still there the title that cause has now — found by kind and
subject, the same task with its history.

Broken on purpose (14 October 2026), each put back by the reverse edit: the
old title back in the source → 3 red ("Refund … bevestigen");
the retitling taken out of the sweep → the old task closed, "the old task
was not given the new title".
"""

from decimal import Decimal

import pytest

from app.domains.payment.api import PaymentRecord, create_refund
from app.domains.workflow.handlers import sweep
from app.domains.workflow.models import TaskStatus, WorkflowTask

pytestmark = pytest.mark.ui_agnostisch


def _pending_refund(db, payable_type: str, payable_id: int):
    charge = PaymentRecord(
        payable_type=payable_type,
        payable_id=payable_id,
        amount=Decimal("30.00"),
        method="transfer",
        status="paid",
    )
    charge.amount_paid = Decimal("30.00")
    db.add(charge)
    db.flush()
    refund = create_refund(db, charge.id, Decimal("10.00"), actor="fin@test", settled=False)
    db.commit()
    return refund


def _open_refund_tasks(db) -> list[WorkflowTask]:
    db.expire_all()
    return (
        db.query(WorkflowTask)
        .filter(
            WorkflowTask.kind == "payment.refund_bevestigen", WorkflowTask.status == TaskStatus.OPEN
        )
        .all()
    )


@pytest.mark.parametrize(
    ("payable_type", "payable_id", "title"),
    [
        ("membership", 19911, "Terugbetaling lidmaatschap #19911 bevestigen"),
        ("registration", 19912, "Terugbetaling inschrijving #19912 bevestigen"),
    ],
)
def test_a_refund_task_names_the_payment_in_words(db_session, payable_type, payable_id, title):
    refund = _pending_refund(db_session, payable_type, payable_id)
    sweep(db_session, {"once": True})
    db_session.commit()

    [task] = [t for t in _open_refund_tasks(db_session) if t.subject_id == str(refund.id)]
    assert task.title == title
    assert str(refund.id) not in task.title and str(refund.id)[:8] not in task.title, task.title


def test_an_open_task_with_the_old_title_gets_the_new_one(db_session):
    refund = _pending_refund(db_session, "membership", 19913)
    old = WorkflowTask(
        kind="payment.refund_bevestigen",
        title=f"Refund {refund.id} bevestigen (membership #19913)",
        status="open",
        subject_type="payment_record",
        subject_id=str(refund.id),
        required_role="FINANCE",
    )
    db_session.add(old)
    db_session.commit()
    old_id = old.id

    sweep(db_session, {"once": True})
    db_session.commit()

    mine = [t for t in _open_refund_tasks(db_session) if t.subject_id == str(refund.id)]
    assert [(t.id, t.title) for t in mine] == [
        (old_id, "Terugbetaling lidmaatschap #19913 bevestigen")
    ], f"the old task was not given the new title: {[(t.id, t.title) for t in mine]}"
    assert db_session.get(WorkflowTask, old_id).status is TaskStatus.OPEN
